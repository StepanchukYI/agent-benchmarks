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
import { useRunsList, useTasksList } from "./api/hooks";

export default function App(): JSX.Element {
  const tasksQ = useTasksList();
  const runsQ = useRunsList();
  const tasksCount = Array.isArray(tasksQ.data) ? tasksQ.data.length : 0;
  const runsCount = Array.isArray(runsQ.data) ? runsQ.data.length : 0;
  return (
    <ThemeProvider>
      <div className="min-h-screen flex flex-col bg-background text-foreground">
        <TopNav counts={{ runs: runsCount, tasks: tasksCount }} />
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
