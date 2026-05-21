import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Navigate, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import Sidebar from "../components/Sidebar";
import { queryClient } from "../lib/queryClient";
import Leaderboard from "../pages/Leaderboard";
import RunLauncher from "../pages/RunLauncher";
import Settings from "../pages/Settings";
import TrajectoryViewer from "../pages/TrajectoryViewer";
import Trends from "../pages/Trends";

function AppForTest(): JSX.Element {
  return (
    <div>
      <Sidebar />
      <main>
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

describe("App", () => {
  it("renders the Leaderboard placeholder at /leaderboard", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/leaderboard"]}>
          <AppForTest />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Phase 0 placeholder/i)).toBeDefined();
    expect(screen.getByRole("heading", { name: /Leaderboard/i })).toBeDefined();
  });
});
