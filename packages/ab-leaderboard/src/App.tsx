import { Navigate, Route, Routes } from "react-router-dom";

import Sidebar from "./components/Sidebar";
import Leaderboard from "./pages/Leaderboard";
import RunLauncher from "./pages/RunLauncher";
import Settings from "./pages/Settings";
import TrajectoryViewer from "./pages/TrajectoryViewer";
import Trends from "./pages/Trends";

export default function App(): JSX.Element {
  return (
    <div className="min-h-screen flex bg-background text-foreground">
      <Sidebar />
      <main className="flex-1 p-6">
        <Routes>
          <Route path="/" element={<Navigate to="/leaderboard" replace />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/runs" element={<RunLauncher />} />
          <Route path="/trajectories" element={<TrajectoryViewer />} />
          <Route path="/trends" element={<Trends />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
