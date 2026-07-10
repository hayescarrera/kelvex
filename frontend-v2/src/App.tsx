import { HashRouter, Route, Routes, Navigate } from "react-router-dom";
import { AppShell } from "./shell/AppShell";
import { Fleet } from "./screens/Fleet";
import { SiteDetail } from "./screens/SiteDetail";
import { AssetDetail } from "./screens/AssetDetail";
import { Alarms } from "./screens/Alarms";
import { Leaks } from "./screens/Leaks";
import { Ledger } from "./screens/Ledger";
import { Compliance } from "./screens/Compliance";
import { Agents } from "./screens/Agents";
import { Admin } from "./screens/Admin";
import { Preferences } from "./screens/Preferences";

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Fleet />} />
          <Route path="/sites/:siteId" element={<SiteDetail />} />
          <Route path="/assets/:assetId" element={<AssetDetail />} />
          <Route path="/alarms" element={<Alarms />} />
          <Route path="/leaks" element={<Leaks />} />
          <Route path="/ledger" element={<Ledger />} />
          <Route path="/compliance" element={<Compliance />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/preferences" element={<Preferences />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
