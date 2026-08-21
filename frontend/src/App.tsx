import { Route, Routes } from "react-router-dom";

import { DashboardLayout } from "./layouts/DashboardLayout";
import { SiteLayout } from "./layouts/SiteLayout";
import { DashboardPage } from "./pages/DashboardPage";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ProtectedRoute } from "./routes/ProtectedRoute";

export default function App() {
  return (
    <Routes>
      <Route element={<SiteLayout />}>
        <Route index element={<LandingPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["patient"]} />}>
        <Route element={<DashboardLayout />}>
          <Route path="patient" element={<DashboardPage role="patient" />} />
        </Route>
      </Route>
      <Route element={<ProtectedRoute allowedRoles={["doctor"]} />}>
        <Route element={<DashboardLayout />}>
          <Route path="doctor" element={<DashboardPage role="doctor" />} />
        </Route>
      </Route>
      <Route element={<ProtectedRoute allowedRoles={["admin"]} />}>
        <Route element={<DashboardLayout />}>
          <Route path="admin" element={<DashboardPage role="admin" />} />
        </Route>
      </Route>
    </Routes>
  );
}

