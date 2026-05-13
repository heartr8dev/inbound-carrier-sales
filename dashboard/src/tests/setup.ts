// Vitest setup — registers @testing-library/jest-dom matchers and provides
// a couple of jsdom polyfills used by visx's responsive layer.
import "@testing-library/jest-dom/vitest";

// visx ParentSize relies on ResizeObserver in real browsers. jsdom lacks it,
// so we stub a minimal version that fires a single notification with a fixed
// size so charts render in tests if anyone needs them.
if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).ResizeObserver = ResizeObserverStub;
}

// IntersectionObserver isn't in jsdom; OutcomeGlyph uses it to trigger
// enter-once animations.
if (typeof globalThis.IntersectionObserver === "undefined") {
  class IntersectionObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).IntersectionObserver = IntersectionObserverStub;
}

// `matchMedia` isn't in jsdom; we use it to detect prefers-reduced-motion.
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}
