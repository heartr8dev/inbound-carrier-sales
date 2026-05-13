// Ambient drifting-dot background. A single full-viewport <canvas> behind the
// app (z-index: -1) that animates ~40 small slate-300 dots at varying speeds
// across the page. Each dot has slight vertical bob to feel organic, and the
// overall opacity is low enough (<= 0.12) that it never competes with data.
//
// Pauses automatically when the user prefers reduced motion or the document
// becomes hidden (saves cycles on the laptop fan).
import { useEffect, useRef } from "react";

interface Particle {
  x: number;
  y: number;
  vx: number; // horizontal velocity
  vy: number; // vertical bob amplitude
  r: number; // radius
  alpha: number;
  phase: number; // bob phase offset
}

export function Particles({ count = 38 }: { count?: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    let dpr = window.devicePixelRatio || 1;
    let width = window.innerWidth;
    let height = window.innerHeight;
    let particles: Particle[] = [];
    let raf: number | null = null;
    let last = performance.now();

    function resize() {
      dpr = window.devicePixelRatio || 1;
      width = window.innerWidth;
      height = window.innerHeight;
      canvas!.width = Math.floor(width * dpr);
      canvas!.height = Math.floor(height * dpr);
      canvas!.style.width = `${width}px`;
      canvas!.style.height = `${height}px`;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function seed() {
      particles = Array.from({ length: count }, () => ({
        // start offscreen-left at random offsets for staggered entry
        x: Math.random() * width,
        y: Math.random() * height,
        // 0.005 → 0.04 px/ms horizontally (~6 → ~48 px/s)
        vx: 0.005 + Math.random() * 0.035,
        vy: 0.15 + Math.random() * 0.6,
        r: 0.7 + Math.random() * 1.4,
        alpha: 0.04 + Math.random() * 0.06,
        phase: Math.random() * Math.PI * 2,
      }));
    }

    function step(now: number) {
      const dt = Math.min(48, now - last); // cap step
      last = now;
      ctx!.clearRect(0, 0, width, height);
      for (const p of particles) {
        p.x += p.vx * dt;
        p.phase += dt * 0.0008;
        const yBob = Math.sin(p.phase) * p.vy;
        if (p.x > width + 6) {
          p.x = -6;
          p.y = Math.random() * height;
        }
        const yy = p.y + yBob;
        ctx!.beginPath();
        ctx!.fillStyle = `rgba(203, 213, 225, ${p.alpha})`; // slate-300
        ctx!.arc(p.x, yy, p.r, 0, Math.PI * 2);
        ctx!.fill();
      }
      raf = requestAnimationFrame(step);
    }

    function pause() {
      if (raf != null) cancelAnimationFrame(raf);
      raf = null;
    }
    function resume() {
      if (raf != null) return;
      last = performance.now();
      raf = requestAnimationFrame(step);
    }

    resize();
    seed();
    if (!reduceMotion) resume();

    function onVisibility() {
      if (document.hidden) pause();
      else if (!reduceMotion) resume();
    }
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      pause();
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [count]);

  return <canvas ref={canvasRef} className="ambient-particles" aria-hidden />;
}
