import { Navigate, Route, Routes } from "react-router-dom";
import { TopNav } from "./components/shell/TopNav";
import { Footer } from "./components/shell/Footer";
import Leaderboard from "./pages/Leaderboard";
import Settings from "./pages/Settings";
import TrajectoryViewer from "./pages/TrajectoryViewer";
import Trends from "./pages/Trends";
import Tasks from "./pages/Tasks";
import { ThemeProvider } from "./lib/theme";
import { useTasksList } from "./api/hooks";

export default function App(): JSX.Element {
  const tasksQ = useTasksList();
  const tasksCount = Array.isArray(tasksQ.data) ? tasksQ.data.length : 0;
  return (
    <ThemeProvider>
      <div className="min-h-screen flex flex-col bg-background text-foreground">
        <TopNav counts={{ tasks: tasksCount }} />
        <Routes>
          <Route path="/" element={<Navigate to="/leaderboard" replace />} />
          <Route path="/leaderboard" element={<Leaderboard />} />
          {/* /runs intentionally dropped from public web: `ab run` is local-only
              CLI flow. Trajectory viewer keeps its deep-link route below for
              shared trajectory inspection (works with submissions in the future). */}
          <Route path="/trajectories" element={<TrajectoryViewer />} />
          <Route path="/trajectories/:runId/:taskId" element={<TrajectoryViewer />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/trends" element={<Trends />} />
          <Route path="/settings" element={<Settings />} />
          {/* fallback: anything else → leaderboard */}
          <Route path="*" element={<Navigate to="/leaderboard" replace />} />
        </Routes>
        <Footer />
      </div>
    </ThemeProvider>
  );
}
