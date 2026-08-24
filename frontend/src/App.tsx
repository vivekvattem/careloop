import { Route, Routes } from "react-router-dom";

import { DashboardLayout } from "./layouts/DashboardLayout";
import { SiteLayout } from "./layouts/SiteLayout";
import { AdminDashboardPage } from "./pages/AdminDashboardPage";
import { DoctorDashboardPage } from "./pages/DoctorDashboardPage";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PatientDashboardPage } from "./pages/PatientDashboardPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ProtectedRoute } from "./routes/ProtectedRoute";

export default function App() {
  return (
    <Routes>
      <Route element={<SiteLayout />}>
        <Route index element={<LandingPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="forgot-password" element={<ForgotPasswordPage />} />
        <Route path="reset-password" element={<ResetPasswordPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={["patient"]} />}>
        <Route element={<DashboardLayout />}>
          <Route path="patient" element={<PatientDashboardPage />} />
        </Route>
      </Route>
      <Route element={<ProtectedRoute allowedRoles={["doctor"]} />}>
        <Route element={<DashboardLayout />}>
          <Route path="doctor" element={<DoctorDashboardPage />} />
        </Route>
      </Route>
      <Route element={<ProtectedRoute allowedRoles={["admin"]} />}>
        <Route element={<DashboardLayout />}>
          <Route path="admin" element={<AdminDashboardPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
