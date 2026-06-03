import { createBrowserRouter } from 'react-router-dom';
import { HomePage } from './pages/HomePage';
import { JobDetailPage } from './pages/JobDetailPage';
import { SearchPage } from './pages/SearchPage';

export const router = createBrowserRouter([
  { path: '/', element: <HomePage /> },
  { path: '/jobs/:id', element: <JobDetailPage /> },
  { path: '/search', element: <SearchPage /> },
]);
