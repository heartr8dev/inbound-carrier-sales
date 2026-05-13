// KpiBar renders four KPI cards from a MetricsResponse.kpi fixture.
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { KpiBar } from "@/components/KpiBar";
import { mockKpi } from "@/tests/fixtures";

describe("KpiBar", () => {
  it("renders all four KPI labels from a MetricsResponse", () => {
    render(<KpiBar data={mockKpi} />);

    expect(screen.getByText(/Calls Today/i)).toBeInTheDocument();
    expect(screen.getByText(/Booked Rate/i)).toBeInTheDocument();
    expect(screen.getByText(/Avg Margin Saved/i)).toBeInTheDocument();
    expect(screen.getByText(/Avg Negotiation Rounds/i)).toBeInTheDocument();
  });

  it("renders the formatted KPI values", () => {
    render(<KpiBar data={mockKpi} />);

    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("31.4%")).toBeInTheDocument();
    expect(screen.getByText("$188")).toBeInTheDocument();
    expect(screen.getByText("1.8")).toBeInTheDocument();
  });

  it("renders exactly four KPI cards", () => {
    const { container } = render(<KpiBar data={mockKpi} />);
    const root = container.querySelector("[data-testid='kpi-bar']");
    expect(root).not.toBeNull();
    // 4 KPI tiles → 4 immediate-child divs of the grid wrapper
    expect(root!.children.length).toBe(4);
  });
});
