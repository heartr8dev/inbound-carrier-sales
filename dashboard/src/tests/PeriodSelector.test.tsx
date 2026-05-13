// PeriodSelector invokes the onPeriodChange callback with the new value.
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PeriodSelector } from "@/components/PeriodSelector";

describe("PeriodSelector", () => {
  it("calls onPeriodChange with the clicked period value", async () => {
    const user = userEvent.setup();
    const handle = vi.fn();
    render(<PeriodSelector value="7d" onPeriodChange={handle} />);

    await user.click(screen.getByRole("tab", { name: "30d" }));
    expect(handle).toHaveBeenCalledTimes(1);
    expect(handle).toHaveBeenCalledWith("30d");

    await user.click(screen.getByRole("tab", { name: "Today" }));
    expect(handle).toHaveBeenCalledWith("today");

    await user.click(screen.getByRole("tab", { name: "All" }));
    expect(handle).toHaveBeenCalledWith("all");
  });

  it("marks the active period via aria-selected", () => {
    render(<PeriodSelector value="30d" onPeriodChange={() => {}} />);
    const active = screen.getByRole("tab", { name: "30d" });
    expect(active).toHaveAttribute("aria-selected", "true");
    const inactive = screen.getByRole("tab", { name: "7d" });
    expect(inactive).toHaveAttribute("aria-selected", "false");
  });
});
