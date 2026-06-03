import { type ButtonHTMLAttributes, type ReactNode } from 'react';
import { Spinner } from './Spinner';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  children: ReactNode;
}

const variantStyles = {
  primary: [
    'bg-accent text-bg font-heading font-bold',
    'hover:bg-opacity-90 hover:shadow-lg hover:shadow-accent/20',
    'active:scale-[0.98]',
    'disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none',
  ].join(' '),
  ghost: [
    'text-text-secondary',
    'hover:text-text-primary hover:bg-surface2',
    'active:bg-border',
  ].join(' '),
  outline: [
    'border border-border text-text-primary',
    'hover:border-accent hover:text-accent',
    'active:bg-surface2',
  ].join(' '),
};

const sizeStyles = {
  sm: 'px-3 py-1.5 text-sm rounded',
  md: 'px-5 py-2.5 text-base rounded-md',
  lg: 'px-8 py-3.5 text-lg rounded-md w-full',
};

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  children,
  disabled,
  className = '',
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={[
        'inline-flex items-center justify-center gap-2',
        'transition-all duration-[120ms] ease-out',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
        variantStyles[variant],
        sizeStyles[size],
        className,
      ].join(' ')}
    >
      {loading && <Spinner size="sm" />}
      {children}
    </button>
  );
}
