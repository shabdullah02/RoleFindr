// web/app/page.test.tsx  (needs a vitest.config.ts with environment: "jsdom", plugins: [react()])
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import Home from "./page";

test("renders", () => {
  render(<Home />);
  expect(screen.getByText("RoleFindr")).toBeTruthy();
});