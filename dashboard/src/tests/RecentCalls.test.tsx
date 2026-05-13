// RecentCalls expands a row on click and shows the transcript summary.
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RecentCalls } from "@/components/RecentCalls";
import { mockRecentCall } from "@/tests/fixtures";

describe("RecentCalls", () => {
  it("renders a row per call and hides the transcript by default", () => {
    render(<RecentCalls calls={[mockRecentCall]} />);
    expect(
      screen.getByTestId(`call-row-${mockRecentCall.call_id}`),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId(
        `call-row-expanded-${mockRecentCall.call_id}`,
      ),
    ).not.toBeInTheDocument();
  });

  it("expands the row and reveals the transcript on click", async () => {
    const user = userEvent.setup();
    render(<RecentCalls calls={[mockRecentCall]} />);

    const row = screen.getByTestId(`call-row-${mockRecentCall.call_id}`);
    await user.click(row);

    expect(
      screen.getByTestId(`call-row-expanded-${mockRecentCall.call_id}`),
    ).toBeInTheDocument();
    expect(
      screen.getByText(mockRecentCall.transcript_summary as string),
    ).toBeInTheDocument();
    expect(row).toHaveAttribute("aria-expanded", "true");
  });

  it("collapses the row when clicked again", async () => {
    const user = userEvent.setup();
    render(<RecentCalls calls={[mockRecentCall]} />);
    const row = screen.getByTestId(`call-row-${mockRecentCall.call_id}`);
    await user.click(row);
    await user.click(row);
    expect(
      screen.queryByTestId(
        `call-row-expanded-${mockRecentCall.call_id}`,
      ),
    ).not.toBeInTheDocument();
  });
});
