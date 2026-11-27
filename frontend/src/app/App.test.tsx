import { render, screen } from "@testing-library/react";

import { App } from "./App";

describe("App", () => {
  it("서비스 이름을 보여 준다", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "NutriSight" })).toBeInTheDocument();
  });
});
