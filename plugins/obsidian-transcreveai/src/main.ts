import {
  App,
  FileSystemAdapter,
  Menu,
  Notice,
  Plugin,
  PluginSettingTab,
  Setting,
  TAbstractFile,
  TFile,
  normalizePath,
} from "obsidian";
import { spawn } from "child_process";
import { access, mkdir, readFile, rm } from "fs/promises";
import * as path from "path";

interface TranscreveAISettings {
  cliPath: string;
  language: string;
  aiMode: "auto" | "off" | "full";
  provider: string;
  outputDirectory: string;
  indexDbPath: string;
  forceReprocess: boolean;
  cleanupArtifacts: boolean;
  overwriteExistingNote: boolean;
  openNoteAfterCreate: boolean;
  noteSuffix: string;
  includeArtifactPaths: boolean;
  extraArgs: string;
  supportedExtensions: string;
}

interface AnalyzePayload {
  ok?: boolean;
  reused_existing?: boolean;
  run_id?: string;
  workdir?: string;
  analysis_path?: string;
  markdown_path?: string;
  source?: string;
  metadata?: Record<string, unknown>;
  warnings?: string[];
  run?: {
    id?: string;
    status?: string;
    output_dir?: string;
    analysis_path?: string;
    markdown_path?: string;
  };
  handoff?: {
    message?: string;
    run_id?: string;
    out?: string;
    knowledge_md?: string;
    analysis_json?: string;
    index_db?: string;
    index_db_scope?: string;
  };
}

const DEFAULT_SETTINGS: TranscreveAISettings = {
  cliPath: "transcreveai",
  language: "pt",
  aiMode: "auto",
  provider: "",
  outputDirectory: "~/.transcreveai/obsidian-runs",
  indexDbPath: "",
  forceReprocess: false,
  cleanupArtifacts: true,
  overwriteExistingNote: true,
  openNoteAfterCreate: true,
  noteSuffix: ".transcricao",
  includeArtifactPaths: false,
  extraArgs: "",
  supportedExtensions: "mp4,mov,m4v,mkv,webm,avi,m4a,mp3,wav,aac,ogg,flac",
};

export default class TranscreveAIPlugin extends Plugin {
  settings: TranscreveAISettings = DEFAULT_SETTINGS;
  private running = new Set<string>();

  async onload(): Promise<void> {
    await this.loadSettings();

    this.addCommand({
      id: "transcribe-active-media",
      name: "Transcribe current video or audio",
      callback: () => {
        void this.transcribeActiveFile();
      },
    });

    this.addRibbonIcon("file-audio", "TranscreveAI: transcribe current media", () => {
      void this.transcribeActiveFile();
    });

    this.registerEvent(
      this.app.workspace.on("file-menu", (menu: Menu, file: TAbstractFile) => {
        if (file instanceof TFile && this.isSupportedMedia(file)) {
          menu.addItem((item) => {
            item
              .setTitle("Transcribe with TranscreveAI")
              .setIcon("file-audio")
              .onClick(() => {
                void this.transcribeFile(file);
              });
          });
        }
      }),
    );

    this.addSettingTab(new TranscreveAISettingTab(this.app, this));
  }

  async loadSettings(): Promise<void> {
    this.settings = {
      ...DEFAULT_SETTINGS,
      ...(await this.loadData()),
    };
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  private async transcribeActiveFile(): Promise<void> {
    const file = this.app.workspace.getActiveFile();
    if (!file || !this.isSupportedMedia(file)) {
      new Notice("Open or select a supported video/audio file first.");
      return;
    }

    await this.transcribeFile(file);
  }

  private async transcribeFile(file: TFile): Promise<void> {
    if (this.running.has(file.path)) {
      new Notice(`TranscreveAI is already processing ${file.name}.`);
      return;
    }

    const adapter = this.app.vault.adapter;
    if (!(adapter instanceof FileSystemAdapter)) {
      new Notice("TranscreveAI requires the desktop filesystem adapter.");
      return;
    }

    this.running.add(file.path);
    const started = new Notice(`TranscreveAI: processing ${file.name}...`, 0);

    try {
      const vaultRoot = adapter.getBasePath();
      const sourcePath = adapter.getFullPath(file.path);
      const outDir = await this.resolveOutputDirectory(vaultRoot);
      const args = this.buildAnalyzeArgs(sourcePath, outDir);
      let payload = await this.runAnalyze(args, vaultRoot);
      let markdownPath = await resolveUsableMarkdownPath(payload);

      if (!markdownPath && shouldRetryWithForce(payload, args)) {
        new Notice("TranscreveAI: previous partial run found; reprocessing...", 5000);
        payload = await this.runAnalyze([...args, "--force"], vaultRoot);
        markdownPath = await resolveUsableMarkdownPath(payload);
      }

      if (!markdownPath) {
        throw new Error(missingMarkdownMessage(payload));
      }

      const generatedMarkdown = await readFile(markdownPath, "utf8");
      const notePath = await this.resolveTranscriptNotePath(file);
      const note = this.buildTranscriptNote(file, payload, generatedMarkdown, vaultRoot);

      await this.upsertNote(notePath, note);
      if (this.settings.cleanupArtifacts) {
        await this.cleanupRunArtifacts(payload, vaultRoot, outDir);
      }
      started.hide();
      new Notice(`TranscreveAI: transcript saved to ${notePath}.`);

      if (this.settings.openNoteAfterCreate) {
        const createdFile = this.app.vault.getAbstractFileByPath(notePath);
        if (createdFile instanceof TFile) {
          await this.app.workspace.getLeaf(false).openFile(createdFile);
        }
      }
    } catch (error) {
      started.hide();
      new Notice(`TranscreveAI failed: ${errorMessage(error)}`, 10000);
      console.error("TranscreveAI Obsidian plugin failed", error);
    } finally {
      this.running.delete(file.path);
    }
  }

  private buildAnalyzeArgs(sourcePath: string, outDir: string): string[] {
    const args: string[] = [];

    if (this.settings.indexDbPath.trim()) {
      args.push("--index-db", expandHome(this.settings.indexDbPath.trim()));
    }

    args.push("analyze", sourcePath, "--json", "--out", outDir);

    if (this.settings.language.trim()) {
      args.push("--language", this.settings.language.trim());
    }

    args.push("--ai", this.settings.aiMode);

    if (this.settings.provider.trim()) {
      args.push("--provider", this.settings.provider.trim());
    }

    if (this.settings.forceReprocess) {
      args.push("--force");
    }

    args.push(...splitExtraArgs(this.settings.extraArgs));
    return args;
  }

  private async runAnalyze(args: string[], vaultRoot: string): Promise<AnalyzePayload> {
    const command = expandHome(this.settings.cliPath.trim() || "transcreveai");
    const result = await runProcess(command, args, buildCliEnv(vaultRoot));
    if (result.code !== 0) {
      throw new Error(cleanProcessError(result.stderr || result.stdout || `exit code ${result.code}`));
    }

    try {
      return JSON.parse(result.stdout) as AnalyzePayload;
    } catch (error) {
      throw new Error(`Could not parse TranscreveAI JSON output: ${errorMessage(error)}`);
    }
  }

  private async cleanupRunArtifacts(
    payload: AnalyzePayload,
    vaultRoot: string,
    outDir: string,
  ): Promise<void> {
    const runId = payloadRunId(payload);
    const workdir = payloadWorkdir(payload);
    if (!runId && !workdir) {
      return;
    }

    if (runId) {
      try {
        await this.removeRunFromIndex(runId, vaultRoot);
      } catch (error) {
        console.warn("TranscreveAI could not remove run from index", error);
      }
    }

    if (workdir && isSafeCleanupPath(workdir, outDir)) {
      try {
        await rm(workdir, { recursive: true, force: true });
      } catch (error) {
        console.warn("TranscreveAI could not remove run artifacts", error);
      }
    }
  }

  private async removeRunFromIndex(runId: string, vaultRoot: string): Promise<void> {
    const args: string[] = [];
    if (this.settings.indexDbPath.trim()) {
      args.push("--index-db", expandHome(this.settings.indexDbPath.trim()));
    }
    args.push("runs", "rm", runId, "--purge", "--force");
    const command = expandHome(this.settings.cliPath.trim() || "transcreveai");
    await runProcess(command, args, buildCliEnv(vaultRoot));
  }

  private async resolveOutputDirectory(vaultRoot: string): Promise<string> {
    const configured = this.settings.outputDirectory.trim() || DEFAULT_SETTINGS.outputDirectory;
    const resolved = path.isAbsolute(expandHome(configured))
      ? expandHome(configured)
      : path.join(vaultRoot, configured);
    await mkdir(resolved, { recursive: true });
    return resolved;
  }

  private async resolveTranscriptNotePath(file: TFile): Promise<string> {
    const suffix = sanitizeNoteSuffix(this.settings.noteSuffix);
    const parent = file.parent?.path ?? "";
    const baseName = file.basename || path.basename(file.name, `.${file.extension}`);
    const preferred = normalizePath(path.posix.join(parent, `${baseName}${suffix}.md`));

    if (this.settings.overwriteExistingNote || !this.app.vault.getAbstractFileByPath(preferred)) {
      return preferred;
    }

    for (let i = 2; i < 1000; i += 1) {
      const candidate = normalizePath(path.posix.join(parent, `${baseName}${suffix} ${i}.md`));
      if (!this.app.vault.getAbstractFileByPath(candidate)) {
        return candidate;
      }
    }

    throw new Error("Could not find an available transcript note name.");
  }

  private async upsertNote(notePath: string, content: string): Promise<void> {
    const existing = this.app.vault.getAbstractFileByPath(notePath);
    if (existing instanceof TFile) {
      await this.app.vault.modify(existing, content);
      return;
    }
    await this.app.vault.create(notePath, content);
  }

  private buildTranscriptNote(
    file: TFile,
    payload: AnalyzePayload,
    generatedMarkdown: string,
    vaultRoot: string,
  ): string {
    const title = getString(payload.metadata?.title) || file.basename;
    const warnings = payload.warnings ?? [];
    const artifactRef = this.artifactReference(payload, vaultRoot);
    const body = normalizeGeneratedMarkdown(generatedMarkdown).trim();
    const frontmatter = [
      "---",
      `title: ${yamlString(`Transcricao - ${title}`)}`,
      "tags:",
      "  - transcreveai",
      "  - transcricao",
      `transcreveai_run_id: ${yamlString(payloadRunId(payload))}`,
      `transcreveai_source: ${yamlString(file.path)}`,
      `transcreveai_created: ${yamlString(new Date().toISOString())}`,
      artifactRef ? `transcreveai_artifacts: ${yamlString(artifactRef)}` : "",
      "---",
    ].filter(Boolean);

    const warningBlock = warnings.length
      ? [``, `> [!warning] Avisos do TranscreveAI`, ...warnings.map((warning) => `> - ${warning}`), ``]
      : [];

    return [
      ...frontmatter,
      "",
      `# Transcricao - ${title}`,
      "",
      `Arquivo original: ![[${escapeWikilink(file.path)}]]`,
      ...warningBlock,
      "",
      body,
      "",
    ].join("\n");
  }

  private artifactReference(payload: AnalyzePayload, vaultRoot: string): string {
    const workdir = payload.workdir || payload.analysis_path || payload.markdown_path || "";
    if (!workdir) {
      return "";
    }

    const relative = relativizeInsideVault(path.resolve(workdir), vaultRoot);
    if (relative) {
      return relative;
    }

    return this.settings.includeArtifactPaths ? workdir : "";
  }

  private isSupportedMedia(file: TFile): boolean {
    const extensions = new Set(
      this.settings.supportedExtensions
        .split(",")
        .map((ext) => ext.trim().toLowerCase().replace(/^\./, ""))
        .filter(Boolean),
    );
    return extensions.has(file.extension.toLowerCase());
  }
}

class TranscreveAISettingTab extends PluginSettingTab {
  plugin: TranscreveAIPlugin;

  constructor(app: App, plugin: TranscreveAIPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    new Setting(containerEl)
      .setName("CLI path")
      .setDesc("Command or absolute path used to run TranscreveAI.")
      .addText((text) =>
        text
          .setPlaceholder("transcreveai")
          .setValue(this.plugin.settings.cliPath)
          .onChange(async (value) => {
            this.plugin.settings.cliPath = value.trim() || DEFAULT_SETTINGS.cliPath;
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("Language")
      .setDesc("Language hint passed to the transcription model.")
      .addText((text) =>
        text
          .setPlaceholder("pt")
          .setValue(this.plugin.settings.language)
          .onChange(async (value) => {
            this.plugin.settings.language = value.trim();
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("AI mode")
      .setDesc("Controls how much AI TranscreveAI may use.")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("auto", "auto")
          .addOption("off", "off")
          .addOption("full", "full")
          .setValue(this.plugin.settings.aiMode)
          .onChange(async (value) => {
            this.plugin.settings.aiMode = value as TranscreveAISettings["aiMode"];
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("Provider")
      .setDesc("Optional provider override, such as openai, local, gemini or anthropic.")
      .addText((text) =>
        text
          .setPlaceholder("default from TranscreveAI")
          .setValue(this.plugin.settings.provider)
          .onChange(async (value) => {
            this.plugin.settings.provider = value.trim();
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("Output directory")
      .setDesc("Temporary TranscreveAI artifacts. Keep this outside the vault if you only want the sibling .md note.")
      .addText((text) =>
        text
          .setPlaceholder("~/.transcreveai/obsidian-runs")
          .setValue(this.plugin.settings.outputDirectory)
          .onChange(async (value) => {
            this.plugin.settings.outputDirectory = value.trim() || DEFAULT_SETTINGS.outputDirectory;
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("Index database")
      .setDesc("Optional --index-db path. Leave empty to use TranscreveAI's default index.")
      .addText((text) =>
        text
          .setPlaceholder("~/.transcreveai/index.db")
          .setValue(this.plugin.settings.indexDbPath)
          .onChange(async (value) => {
            this.plugin.settings.indexDbPath = value.trim();
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("Note suffix")
      .setDesc("Suffix for the transcript note created next to the media file.")
      .addText((text) =>
        text
          .setPlaceholder(".transcricao")
          .setValue(this.plugin.settings.noteSuffix)
          .onChange(async (value) => {
            this.plugin.settings.noteSuffix = value.trim() || DEFAULT_SETTINGS.noteSuffix;
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("Supported extensions")
      .setDesc("Comma-separated video/audio extensions shown in the context menu.")
      .addTextArea((text) =>
        text
          .setPlaceholder(DEFAULT_SETTINGS.supportedExtensions)
          .setValue(this.plugin.settings.supportedExtensions)
          .onChange(async (value) => {
            this.plugin.settings.supportedExtensions =
              value.trim() || DEFAULT_SETTINGS.supportedExtensions;
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("Extra CLI arguments")
      .setDesc("Optional advanced arguments appended to transcreveai analyze.")
      .addText((text) =>
        text
          .setPlaceholder("--max-frames 60")
          .setValue(this.plugin.settings.extraArgs)
          .onChange(async (value) => {
            this.plugin.settings.extraArgs = value.trim();
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("Force reprocess")
      .setDesc("Pass --force when TranscreveAI already has a run for the same source.")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.forceReprocess).onChange(async (value) => {
          this.plugin.settings.forceReprocess = value;
          await this.plugin.saveSettings();
        }),
      );

    new Setting(containerEl)
      .setName("Clean temporary artifacts")
      .setDesc("After the note is created, remove the raw TranscreveAI run files and index entry.")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.cleanupArtifacts).onChange(async (value) => {
          this.plugin.settings.cleanupArtifacts = value;
          await this.plugin.saveSettings();
        }),
      );

    new Setting(containerEl)
      .setName("Overwrite existing transcript note")
      .setDesc("Update nome.transcricao.md instead of creating numbered copies.")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.overwriteExistingNote).onChange(async (value) => {
          this.plugin.settings.overwriteExistingNote = value;
          await this.plugin.saveSettings();
        }),
      );

    new Setting(containerEl)
      .setName("Open note after transcription")
      .setDesc("Open the generated transcript note when the run finishes.")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.openNoteAfterCreate).onChange(async (value) => {
          this.plugin.settings.openNoteAfterCreate = value;
          await this.plugin.saveSettings();
        }),
      );

    new Setting(containerEl)
      .setName("Include absolute artifact paths")
      .setDesc("Only use this when you want external artifact paths written into notes.")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.includeArtifactPaths).onChange(async (value) => {
          this.plugin.settings.includeArtifactPaths = value;
          await this.plugin.saveSettings();
        }),
      );
  }
}

interface ProcessResult {
  code: number;
  stdout: string;
  stderr: string;
}

function runProcess(
  command: string,
  args: string[],
  env: NodeJS.ProcessEnv = process.env,
): Promise<ProcessResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      env,
      shell: false,
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      resolve({ code: code ?? 1, stdout, stderr });
    });
  });
}

function buildCliEnv(vaultRoot: string): NodeJS.ProcessEnv {
  return {
    ...process.env,
    VIDEO_KB_ALLOWED_LOCAL_SOURCE_ROOTS: appendPathListValue(
      process.env.VIDEO_KB_ALLOWED_LOCAL_SOURCE_ROOTS,
      vaultRoot,
    ),
  };
}

function appendPathListValue(existing: string | undefined, value: string): string {
  const parts = (existing || "")
    .split(path.delimiter)
    .map((part) => part.trim())
    .filter(Boolean);
  if (!parts.includes(value)) {
    parts.push(value);
  }
  return parts.join(path.delimiter);
}

function splitExtraArgs(input: string): string[] {
  const result: string[] = [];
  let current = "";
  let quote: "'" | '"' | null = null;

  for (let i = 0; i < input.length; i += 1) {
    const char = input[i];
    if ((char === "'" || char === '"') && quote === null) {
      quote = char;
      continue;
    }
    if (quote === char) {
      quote = null;
      continue;
    }
    if (/\s/.test(char) && quote === null) {
      if (current) {
        result.push(current);
        current = "";
      }
      continue;
    }
    current += char;
  }

  if (current) {
    result.push(current);
  }

  return result;
}

function stripLeadingFrontmatter(markdown: string): string {
  return markdown.replace(/^---\n[\s\S]*?\n---\n?/, "");
}

function normalizeGeneratedMarkdown(markdown: string): string {
  return stripLeadingFrontmatter(markdown)
    .split("\n")
    .filter((line) => !line.trim().match(/^!\[frame\]\(frames\/[^)]+\)$/))
    .join("\n");
}

function yamlString(value: string): string {
  return JSON.stringify(value);
}

function escapeWikilink(pathValue: string): string {
  return pathValue.replace(/\|/g, "\\|");
}

function sanitizeNoteSuffix(value: string): string {
  const suffix = value.trim() || DEFAULT_SETTINGS.noteSuffix;
  return suffix.endsWith(".md") ? suffix.slice(0, -3) : suffix;
}

function expandHome(value: string): string {
  if (value === "~") {
    return process.env.HOME || value;
  }
  if (value.startsWith("~/")) {
    return path.join(process.env.HOME || "~", value.slice(2));
  }
  return value;
}

function relativizeInsideVault(value: string, vaultRoot: string): string {
  const relative = path.relative(vaultRoot, value);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
    return "";
  }
  return normalizePath(relative);
}

async function resolveUsableMarkdownPath(payload: AnalyzePayload): Promise<string> {
  const candidates = [
    payload.markdown_path,
    payload.handoff?.knowledge_md,
    payload.run?.markdown_path,
    payload.workdir ? path.join(payload.workdir, "knowledge.md") : "",
    payload.handoff?.out ? path.join(payload.handoff.out, "knowledge.md") : "",
    payload.run?.output_dir ? path.join(payload.run.output_dir, "knowledge.md") : "",
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const candidate of candidates) {
    if (await fileExists(candidate)) {
      return candidate;
    }
  }

  return "";
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

function shouldRetryWithForce(payload: AnalyzePayload, args: string[]): boolean {
  if (!payload.reused_existing || args.includes("--force")) {
    return false;
  }

  const status = payload.run?.status ?? "";
  return !payload.ok || !payload.run?.markdown_path || status === "partial";
}

function missingMarkdownMessage(payload: AnalyzePayload): string {
  const status = payload.run?.status ? ` status=${payload.run.status}` : "";
  const runId = payloadRunId(payload);
  const id = runId ? ` run_id=${runId}` : "";
  return `TranscreveAI did not produce a readable knowledge.md.${id}${status}`;
}

function payloadRunId(payload: AnalyzePayload): string {
  return payload.run_id ?? payload.handoff?.run_id ?? payload.run?.id ?? "";
}

function payloadWorkdir(payload: AnalyzePayload): string {
  return payload.workdir ?? payload.handoff?.out ?? payload.run?.output_dir ?? "";
}

function isSafeCleanupPath(workdir: string, outDir: string): boolean {
  try {
    const root = path.resolve(outDir);
    const target = path.resolve(workdir);
    const relative = path.relative(root, target);
    return Boolean(relative) && !relative.startsWith("..") && !path.isAbsolute(relative);
  } catch {
    return false;
  }
}

function cleanProcessError(value: string): string {
  return value.trim().split("\n").slice(-4).join("\n");
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function getString(value: unknown): string {
  return typeof value === "string" ? value : "";
}
