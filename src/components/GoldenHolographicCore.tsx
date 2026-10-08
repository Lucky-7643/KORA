import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { ElysiaAudioSession, LiveState } from "../lib/audio";
import { type ElysiaEmotion } from "./ElysiaCoreVisualizer";

interface GoldenHolographicCoreProps {
  session: ElysiaAudioSession | null;
  state: LiveState;
  characterState: "idle" | "thinking" | "talking";
  activeEmotion?: ElysiaEmotion;
}

/**
 * Creates a soft glowing circular particle texture procedurally via 2D Canvas.
 */
function createParticleTexture(): THREE.Texture {
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const gradient = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
    gradient.addColorStop(0, "rgba(255, 255, 255, 1)");
    gradient.addColorStop(0.2, "rgba(255, 230, 130, 0.95)");
    gradient.addColorStop(0.45, "rgba(255, 175, 40, 0.6)");
    gradient.addColorStop(0.75, "rgba(220, 110, 10, 0.2)");
    gradient.addColorStop(1, "rgba(0, 0, 0, 0)");

    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 64, 64);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

/**
 * Creates an intense lens flare / starburst core texture procedurally.
 */
function createCoreGlowTexture(): THREE.Texture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const cx = 128;
    const cy = 128;
    const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, 128);
    gradient.addColorStop(0, "rgba(255, 255, 255, 1)");
    gradient.addColorStop(0.12, "rgba(255, 235, 160, 0.9)");
    gradient.addColorStop(0.3, "rgba(255, 180, 45, 0.5)");
    gradient.addColorStop(0.6, "rgba(230, 120, 10, 0.15)");
    gradient.addColorStop(1, "rgba(0, 0, 0, 0)");

    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 256, 256);

    // Cross flare rays
    ctx.strokeStyle = "rgba(255, 230, 150, 0.35)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(0, cy);
    ctx.lineTo(256, cy);
    ctx.moveTo(cx, 0);
    ctx.lineTo(cx, 256);
    ctx.stroke();

    // Diagonal subtle rays
    ctx.strokeStyle = "rgba(255, 190, 80, 0.15)";
    ctx.beginPath();
    ctx.moveTo(30, 30);
    ctx.lineTo(226, 226);
    ctx.moveTo(30, 226);
    ctx.lineTo(226, 30);
    ctx.stroke();
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

/**
 * Creates segmented circular HUD ring geometries with tick marks and arcs.
 */
function createHudRingGeometry(
  radius: number,
  segments: number,
  arcCoverage: number = 0.85,
  gapCount: number = 4
): THREE.BufferGeometry {
  const points: THREE.Vector3[] = [];
  const arcPerSegment = (Math.PI * 2) / gapCount;
  const activeArc = arcPerSegment * arcCoverage;

  for (let g = 0; g < gapCount; g++) {
    const startAngle = g * arcPerSegment;
    const endAngle = startAngle + activeArc;
    const subSteps = Math.floor(segments / gapCount);

    for (let s = 0; s < subSteps; s++) {
      const a1 = startAngle + (s / subSteps) * activeArc;
      const a2 = startAngle + ((s + 1) / subSteps) * activeArc;

      points.push(
        new THREE.Vector3(Math.cos(a1) * radius, Math.sin(a1) * radius, 0)
      );
      points.push(
        new THREE.Vector3(Math.cos(a2) * radius, Math.sin(a2) * radius, 0)
      );
    }
  }

  return new THREE.BufferGeometry().setFromPoints(points);
}

/**
 * Creates an astrolabe dial ring with radial tick marks.
 */
function createTickRingGeometry(
  radius: number,
  tickLength: number,
  tickCount: number
): THREE.BufferGeometry {
  const points: THREE.Vector3[] = [];
  for (let i = 0; i < tickCount; i++) {
    const angle = (i / tickCount) * Math.PI * 2;
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    const isMajor = i % 4 === 0;
    const len = isMajor ? tickLength * 1.8 : tickLength;

    points.push(new THREE.Vector3(cos * (radius - len * 0.5), sin * (radius - len * 0.5), 0));
    points.push(new THREE.Vector3(cos * (radius + len * 0.5), sin * (radius + len * 0.5), 0));
  }
  return new THREE.BufferGeometry().setFromPoints(points);
}

export const GoldenHolographicCore: React.FC<GoldenHolographicCoreProps> = ({
  session,
  state,
  characterState,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Interaction dragging & rotation physics
  const isDraggingRef = useRef<boolean>(false);
  const previousPointerRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const rotationVelocityRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const targetRotationRef = useRef<{ x: number; y: number }>({ x: 0.15, y: 0 });
  const mouseHoverRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const zoomDistanceRef = useRef<number>(2.8);
  const targetZoomRef = useRef<number>(2.8);

  // Audio reactivity refs
  const smoothedAudioRef = useRef<number>(0);
  const audioDataRef = useRef<Uint8Array<ArrayBuffer>>(new Uint8Array(64));

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // ─── 1. Scene & Camera Setup ─────────────────────────────────────
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x060400, 0.08);

    const camera = new THREE.PerspectiveCamera(
      45,
      container.clientWidth / container.clientHeight,
      0.1,
      100
    );
    camera.position.set(0, 0, zoomDistanceRef.current);

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.25;
    container.appendChild(renderer.domElement);

    const particleTexture = createParticleTexture();
    const coreGlowTexture = createCoreGlowTexture();

    // Hologram Main Pivot Group (rotates with user drag & ambient spin)
    const holoSphereGroup = new THREE.Group();
    scene.add(holoSphereGroup);

    // ─── 2. Golden Spherical Particle Cloud (Shells) ──────────────────
    const PARTICLE_COUNT = 3400;
    const particlePositions = new Float32Array(PARTICLE_COUNT * 3);
    const particleColors = new Float32Array(PARTICLE_COUNT * 3);
    const particleSizes = new Float32Array(PARTICLE_COUNT);
    const particleOriginals = new Float32Array(PARTICLE_COUNT * 3);
    const particleSpeeds = new Float32Array(PARTICLE_COUNT);

    const goldenPalette = [
      new THREE.Color("#FFE97F"), // Brilliant bright gold
      new THREE.Color("#FFC83B"), // Vivid amber gold
      new THREE.Color("#FFA41B"), // Deep golden orange
      new THREE.Color("#F86F03"), // Radiant fiery amber
      new THREE.Color("#FFF6BD"), // Radiant white-gold highlight
    ];

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const idx = i * 3;
      // Fibonacci sphere distribution with layered shell radii
      const shellType = Math.random();
      let radius = 0.95;
      if (shellType < 0.45) {
        // Main outer sphere
        radius = 0.92 + Math.random() * 0.16;
      } else if (shellType < 0.75) {
        // Concentric inner shells
        radius = 0.55 + Math.random() * 0.25;
      } else if (shellType < 0.9) {
        // Equatorial dense rings
        radius = 0.85 + Math.random() * 0.28;
      } else {
        // Core halo
        radius = 0.18 + Math.random() * 0.28;
      }

      const phi = Math.acos(-1 + (2 * i) / PARTICLE_COUNT);
      const theta = Math.sqrt(PARTICLE_COUNT * Math.PI) * phi;

      const x = radius * Math.cos(theta) * Math.sin(phi);
      const y = radius * Math.sin(theta) * Math.sin(phi);
      const z = radius * Math.cos(phi);

      particlePositions[idx] = x;
      particlePositions[idx + 1] = y;
      particlePositions[idx + 2] = z;

      particleOriginals[idx] = x;
      particleOriginals[idx + 1] = y;
      particleOriginals[idx + 2] = z;

      const col = goldenPalette[Math.floor(Math.random() * goldenPalette.length)];
      particleColors[idx] = col.r;
      particleColors[idx + 1] = col.g;
      particleColors[idx + 2] = col.b;

      particleSizes[i] = Math.random() * 0.045 + 0.018;
      particleSpeeds[i] = (Math.random() * 0.8 + 0.4) * (Math.random() > 0.5 ? 1 : -1);
    }

    const particleGeometry = new THREE.BufferGeometry();
    particleGeometry.setAttribute("position", new THREE.BufferAttribute(particlePositions, 3));
    particleGeometry.setAttribute("color", new THREE.BufferAttribute(particleColors, 3));
    particleGeometry.setAttribute("size", new THREE.BufferAttribute(particleSizes, 1));

    const particleMaterial = new THREE.PointsMaterial({
      size: 0.04,
      map: particleTexture,
      transparent: true,
      blending: THREE.AdditiveBlending,
      vertexColors: true,
      depthWrite: false,
      opacity: 0.88,
    });

    const particles = new THREE.Points(particleGeometry, particleMaterial);
    holoSphereGroup.add(particles);

    // ─── 3. Concentric Astrolabe HUD Rings (Iron Man / Jarvis Aesthetic) ─
    const hudRings: Array<{
      object: THREE.Object3D;
      axis: THREE.Vector3;
      speed: number;
      baseScale: number;
    }> = [];

    const ringLineMaterial = new THREE.LineBasicMaterial({
      color: 0xffbe3b,
      transparent: true,
      opacity: 0.55,
      blending: THREE.AdditiveBlending,
      linewidth: 1,
    });

    const ringBrightLineMaterial = new THREE.LineBasicMaterial({
      color: 0xffea85,
      transparent: true,
      opacity: 0.8,
      blending: THREE.AdditiveBlending,
      linewidth: 1,
    });

    const ringAmberLineMaterial = new THREE.LineBasicMaterial({
      color: 0xf58a07,
      transparent: true,
      opacity: 0.45,
      blending: THREE.AdditiveBlending,
      linewidth: 1,
    });

    // Ring 1: Primary Equatorial Segmented Ring
    const ring1Geom = createHudRingGeometry(1.05, 128, 0.88, 6);
    const ring1 = new THREE.LineSegments(ring1Geom, ringBrightLineMaterial);
    ring1.rotation.x = Math.PI * 0.5;
    holoSphereGroup.add(ring1);
    hudRings.push({ object: ring1, axis: new THREE.Vector3(0, 1, 0), speed: 0.25, baseScale: 1.0 });

    // Ring 2: Astrolabe Ticked Ring (Inclined 30 degrees)
    const tickRingGeom = createTickRingGeometry(1.12, 0.04, 72);
    const tickRing = new THREE.LineSegments(tickRingGeom, ringLineMaterial);
    tickRing.rotation.set(Math.PI * 0.18, Math.PI * 0.1, 0);
    holoSphereGroup.add(tickRing);
    hudRings.push({ object: tickRing, axis: new THREE.Vector3(0.3, 1, 0.2).normalize(), speed: -0.18, baseScale: 1.0 });

    // Ring 3: Polar Latitude Orbit Ring (Inclined 70 degrees)
    const ring3Geom = createHudRingGeometry(0.98, 96, 0.75, 4);
    const ring3 = new THREE.LineSegments(ring3Geom, ringAmberLineMaterial);
    ring3.rotation.set(Math.PI * 0.4, 0, Math.PI * 0.25);
    holoSphereGroup.add(ring3);
    hudRings.push({ object: ring3, axis: new THREE.Vector3(-0.5, 0.8, 0.3).normalize(), speed: 0.35, baseScale: 1.0 });

    // Ring 4: Inner High-Speed Astrolabe Dial
    const ring4Geom = createTickRingGeometry(0.68, 0.025, 48);
    const ring4 = new THREE.LineSegments(ring4Geom, ringBrightLineMaterial);
    ring4.rotation.set(-Math.PI * 0.25, Math.PI * 0.3, 0);
    holoSphereGroup.add(ring4);
    hudRings.push({ object: ring4, axis: new THREE.Vector3(0.2, 0.9, -0.4).normalize(), speed: -0.55, baseScale: 1.0 });

    // Ring 5: Giant Outer Horizon Guard Ring with 8 arc segments
    const ring5Geom = createHudRingGeometry(1.22, 160, 0.65, 8);
    const ring5 = new THREE.LineSegments(ring5Geom, ringAmberLineMaterial);
    ring5.rotation.set(0.2, -0.4, 0.6);
    holoSphereGroup.add(ring5);
    hudRings.push({ object: ring5, axis: new THREE.Vector3(0.1, 1, 0.1).normalize(), speed: 0.12, baseScale: 1.0 });

    // ─── 4. Central Radiant Holographic Core ─────────────────────────
    const coreSpriteMat = new THREE.SpriteMaterial({
      map: coreGlowTexture,
      color: 0xffffff,
      transparent: true,
      blending: THREE.AdditiveBlending,
      opacity: 0.95,
      depthWrite: false,
    });
    const coreSprite = new THREE.Sprite(coreSpriteMat);
    coreSprite.scale.set(0.6, 0.6, 1);
    holoSphereGroup.add(coreSprite);

    const outerCoronaMat = new THREE.SpriteMaterial({
      map: coreGlowTexture,
      color: 0xffaa22,
      transparent: true,
      blending: THREE.AdditiveBlending,
      opacity: 0.5,
      depthWrite: false,
    });
    const outerCorona = new THREE.Sprite(outerCoronaMat);
    outerCorona.scale.set(1.4, 1.4, 1);
    holoSphereGroup.add(outerCorona);

    // ─── 5. Ambient Stardust Sparks ──────────────────────────────────
    const DUST_COUNT = 300;
    const dustPositions = new Float32Array(DUST_COUNT * 3);
    for (let i = 0; i < DUST_COUNT; i++) {
      dustPositions[i * 3] = (Math.random() - 0.5) * 3.5;
      dustPositions[i * 3 + 1] = (Math.random() - 0.5) * 3.5;
      dustPositions[i * 3 + 2] = (Math.random() - 0.5) * 3.5;
    }
    const dustGeometry = new THREE.BufferGeometry();
    dustGeometry.setAttribute("position", new THREE.BufferAttribute(dustPositions, 3));
    const dustMaterial = new THREE.PointsMaterial({
      size: 0.025,
      map: particleTexture,
      color: 0xffc745,
      transparent: true,
      opacity: 0.45,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const dustParticles = new THREE.Points(dustGeometry, dustMaterial);
    scene.add(dustParticles);

    // ─── 6. Event Handlers: Drag & Parallax & Zoom ───────────────────
    const handlePointerDown = (e: PointerEvent) => {
      isDraggingRef.current = true;
      previousPointerRef.current = { x: e.clientX, y: e.clientY };
      rotationVelocityRef.current = { x: 0, y: 0 };
    };

    const handlePointerMove = (e: PointerEvent) => {
      const rect = container.getBoundingClientRect();
      const nx = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      const ny = -(((e.clientY - rect.top) / rect.height) * 2 - 1);
      mouseHoverRef.current = { x: nx, y: ny };

      if (isDraggingRef.current) {
        const deltaX = e.clientX - previousPointerRef.current.x;
        const deltaY = e.clientY - previousPointerRef.current.y;

        const factor = 0.005;
        targetRotationRef.current.y += deltaX * factor;
        targetRotationRef.current.x += deltaY * factor;

        rotationVelocityRef.current = {
          x: deltaY * factor,
          y: deltaX * factor,
        };

        previousPointerRef.current = { x: e.clientX, y: e.clientY };
      }
    };

    const handlePointerUp = () => {
      isDraggingRef.current = false;
    };

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      const zoomDelta = e.deltaY * 0.0015;
      targetZoomRef.current = Math.max(1.6, Math.min(4.8, targetZoomRef.current + zoomDelta));
    };

    container.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    container.addEventListener("wheel", handleWheel, { passive: false });

    // Handle Resize
    const resizeObserver = new ResizeObserver(() => {
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });
    resizeObserver.observe(container);

    // ─── 7. Main High-Performance Animation Loop ─────────────────────
    let animationFrameId: number;
    let clock = new THREE.Clock();

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);

      const delta = clock.getDelta();
      const elapsedTime = clock.getElapsedTime();

      // Audio Frequency analysis from session
      let audioLevel = 0;
      let activeAnalyser = null;
      if (state === "speaking" && session?.outputAnalyser) {
        activeAnalyser = session.outputAnalyser;
      } else if (state === "listening" && session?.inputAnalyser) {
        activeAnalyser = session.inputAnalyser;
      }

      if (activeAnalyser) {
        try {
          activeAnalyser.getByteFrequencyData(audioDataRef.current);
          let sum = 0;
          for (let i = 0; i < audioDataRef.current.length; i++) {
            sum += audioDataRef.current[i];
          }
          audioLevel = sum / (audioDataRef.current.length * 255);
        } catch {
          // Analyser closed or detached
        }
      }

      // Smooth audio responsiveness
      smoothedAudioRef.current += (audioLevel - smoothedAudioRef.current) * 0.22;
      const audioBoost = smoothedAudioRef.current;

      // Momentum Inertia & Smooth Drag Rotation
      if (!isDraggingRef.current) {
        // Natural ambient rotation speed depends on state
        const stateSpeedMultiplier =
          characterState === "thinking"
            ? 3.2
            : characterState === "talking"
            ? 1.8 + audioBoost * 2.0
            : 0.8;

        targetRotationRef.current.y +=
          (0.35 * stateSpeedMultiplier * delta + rotationVelocityRef.current.y);
        targetRotationRef.current.x += rotationVelocityRef.current.x;

        // Velocity damping
        rotationVelocityRef.current.x *= 0.94;
        rotationVelocityRef.current.y *= 0.94;
      }

      // Smoothly interpolate holoSphere rotation
      holoSphereGroup.rotation.x = THREE.MathUtils.lerp(
        holoSphereGroup.rotation.x,
        targetRotationRef.current.x + mouseHoverRef.current.y * 0.12,
        0.08
      );
      holoSphereGroup.rotation.y = THREE.MathUtils.lerp(
        holoSphereGroup.rotation.y,
        targetRotationRef.current.y + mouseHoverRef.current.x * 0.15,
        0.08
      );

      // Smooth Camera Zoom
      zoomDistanceRef.current = THREE.MathUtils.lerp(
        zoomDistanceRef.current,
        targetZoomRef.current,
        0.08
      );
      camera.position.z = zoomDistanceRef.current;

      // Animate Individual HUD Rings
      hudRings.forEach((ring) => {
        const speedMultiplier =
          characterState === "thinking"
            ? 2.8
            : characterState === "talking"
            ? 1.6 + audioBoost * 1.5
            : 1.0;

        ring.object.rotateOnAxis(ring.axis, ring.speed * speedMultiplier * delta);

        // Ring audio expansion bounce
        const scaleVal = ring.baseScale * (1.0 + audioBoost * 0.18);
        ring.object.scale.set(scaleVal, scaleVal, scaleVal);
      });

      // Animate Particles: swirling turbulence & audio pulsation
      const positions = particleGeometry.attributes.position.array as Float32Array;
      const swirlFactor = characterState === "thinking" ? 2.5 : 1.0;

      for (let i = 0; i < PARTICLE_COUNT; i++) {
        const idx = i * 3;
        const ox = particleOriginals[idx];
        const oy = particleOriginals[idx + 1];
        const oz = particleOriginals[idx + 2];
        const spd = particleSpeeds[i];

        // Orbit oscillation around Y-axis
        const angle = elapsedTime * spd * 0.3 * swirlFactor;
        const cos = Math.cos(angle);
        const sin = Math.sin(angle);

        // Audio radial dilation
        const radiusMultiplier = 1.0 + audioBoost * 0.22 + Math.sin(elapsedTime * 2 + i) * 0.02;

        positions[idx] = (ox * cos - oz * sin) * radiusMultiplier;
        positions[idx + 1] = (oy + Math.sin(elapsedTime * 1.5 + i * 0.5) * 0.03) * radiusMultiplier;
        positions[idx + 2] = (ox * sin + oz * cos) * radiusMultiplier;
      }
      particleGeometry.attributes.position.needsUpdate = true;

      // Dynamic Particle Sparkle Size
      particleMaterial.size = 0.038 + audioBoost * 0.045;

      // Animate Central Core Glow & Flare
      const corePulse = 1.0 + Math.sin(elapsedTime * 3.5) * 0.08 + audioBoost * 0.6;
      coreSprite.scale.set(0.65 * corePulse, 0.65 * corePulse, 1);
      coreSpriteMat.opacity = Math.min(1.0, 0.85 + audioBoost * 0.5);

      const coronaPulse = 1.0 + Math.sin(elapsedTime * 2.0) * 0.12 + audioBoost * 0.85;
      outerCorona.scale.set(1.4 * coronaPulse, 1.4 * coronaPulse, 1);
      outerCoronaMat.opacity = Math.min(0.85, 0.45 + audioBoost * 0.6);

      // Ambient Stardust gentle drift
      dustParticles.rotation.y = elapsedTime * 0.04;
      dustParticles.rotation.x = elapsedTime * 0.02;

      renderer.render(scene, camera);
    };

    animate();

    // ─── 8. Cleanup ──────────────────────────────────────────────────
    return () => {
      cancelAnimationFrame(animationFrameId);
      resizeObserver.disconnect();
      container.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      container.removeEventListener("wheel", handleWheel);

      // Dispose Three.js objects cleanly
      particleGeometry.dispose();
      particleMaterial.dispose();
      particleTexture.dispose();
      coreGlowTexture.dispose();
      dustGeometry.dispose();
      dustMaterial.dispose();
      ringLineMaterial.dispose();
      ringBrightLineMaterial.dispose();
      ringAmberLineMaterial.dispose();
      coreSpriteMat.dispose();
      outerCoronaMat.dispose();

      hudRings.forEach((r) => {
        if ("geometry" in r.object && r.object.geometry) {
          (r.object.geometry as THREE.BufferGeometry).dispose();
        }
      });

      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [session, state, characterState]);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full flex items-center justify-center cursor-grab active:cursor-grabbing select-none touch-none"
      title="Click and drag to rotate the holographic core in 3D"
    >
      {/* HUD Radial Status Ring Overlay (Stylized SVG Accents) */}
      <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
        <div className="w-[85vmin] h-[85vmin] rounded-full border border-amber-500/10 pointer-events-none animate-[spin_60s_linear_infinite]" />
        <div className="w-[105vmin] h-[105vmin] rounded-full border border-dashed border-amber-500/10 pointer-events-none animate-[spin_90s_linear_infinite_reverse]" />
      </div>

      {/* Floating Tactical Coordinate Badges */}
      <div className="absolute bottom-8 left-10 pointer-events-none font-mono text-[10px] tracking-widest text-amber-500/60 uppercase hidden sm:block">
        <div className="flex items-center gap-2 mb-1">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse shadow-[0_0_8px_#f59e0b]" />
          <span>HOLO-CORE STABILITY : 99.8%</span>
        </div>
        <div className="text-amber-500/40">GEO-LOCK: 3D ROTATION MATRIX READY</div>
      </div>

      <div className="absolute bottom-8 right-10 pointer-events-none font-mono text-[10px] tracking-widest text-amber-500/60 uppercase hidden sm:block text-right">
        <div className="text-amber-400/80 mb-1">MODE: {characterState.toUpperCase()}</div>
        <div className="text-amber-500/40">DRAG TO ROTATE • SCROLL TO ZOOM</div>
      </div>
    </div>
  );
};
