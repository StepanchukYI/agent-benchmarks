import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import Leaderboard from "../pages/Leaderboard";
import Settings from "../pages/Settings";
import Tasks from "../pages/Tasks";
import TrajectoryViewer from "../pages/TrajectoryViewer";
import Trends from "../pages/Trends";
import { queryClient } from "../lib/queryClient";
import { ThemeProvider } from "../lib/theme";

function withRoute(path: string, element: JSX.Element): JSX.Element {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={path} element={element} />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

describe("Pages — smoke", () => {
  it("renders Leaderboard with at least one model row", () => {
    render(withRoute("/leaderboard", <Leaderboard />));
    expect(screen.getByRole("heading", { name: /Leaderboard/i })).toBeDefined();
    expect(screen.getByText(/Mean correctness/i)).toBeDefined();
  });

  it("renders Tasks library with the task tree", () => {
    render(withRoute("/tasks", <Tasks />));
    expect(screen.getByRole("heading", { name: /Task library/i })).toBeDefined();
  });

  it("renders Trajectory viewer with the provenance breadcrumb", () => {
    render(withRoute("/trajectories", <TrajectoryViewer />));
    expect(screen.getAllByText(/@evgeniy/i).length).toBeGreaterThan(0);
  });

  it("renders Trends with overview cards", () => {
    render(withRoute("/trends", <Trends />));
    expect(screen.getByRole("heading", { name: /Trends/i })).toBeDefined();
    expect(screen.getByText(/Active regressions/i)).toBeDefined();
  });

  it("renders Settings with the Account tab open by default", () => {
    render(withRoute("/settings", <Settings />));
    expect(screen.getByRole("heading", { name: /Account/i })).toBeDefined();
    expect(screen.getAllByText(/GitHub identity/i).length).toBeGreaterThan(0);
  });
});
