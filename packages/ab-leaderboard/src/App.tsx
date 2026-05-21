import { Navigate, Route, Routes } from "react-router-dom";
import { TopNav } from "./components/shell/TopNav";
import { Footer } from "./components/shell/Footer";
import Leaderboard from "./pages/Leaderboard";
import RunLauncher from "./pages/RunLauncher";
import Settings from "./pages/Settings";
import TrajectoryViewer from "./pages/TrajectoryViewer";
import Trends from "./pages/Trends";
import Tasks from "./pages/Tasks";
import { ThemeProvider } from "./lib/theme";

export default function App(): JSX.Element {
  return (
    <ThemeProvider>
      <div className="min-h-screen flex flex-col bg-background text-foreground">
        <TopNav counts={{ runs: 12, tasks: 159 }} />
        <Routes>
          <Route path="/" element={<Navigate to="/leaderboard" replace />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          <Route path="/runs" element={<RunLauncher />} />
          <Route path="/runs/:runId/trajectories/:taskId" element={<TrajectoryViewer />} />
          <Route path="/trajectories" element={<TrajectoryViewer />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/trends" element={<Trends />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
        <Footer />
      </div>
    </ThemeProvider>
  );
}
