import { LandingPage } from '../../pages/static/@custom/LandingPage';
import { SignupPage } from '../../pages/static/@custom/SignupPage';

export const customRoutes = [
  { path: '/', element: <LandingPage /> },
  { path: '/signup', element: <SignupPage /> },
];