import { motion } from "framer-motion";

const ORBS = [
  { size: 400, x: "10%", y: "5%", delay: 0, duration: 20 },
  { size: 300, x: "70%", y: "15%", delay: 3, duration: 24 },
  { size: 250, x: "40%", y: "55%", delay: 1, duration: 18 },
  { size: 200, x: "80%", y: "70%", delay: 5, duration: 22 },
  { size: 160, x: "20%", y: "80%", delay: 2, duration: 16 },
];

export default function AmbientBackground() {
  return (
    <div className="ambient-bg" aria-hidden="true">
      <div className="dot-grid" />

      {ORBS.map((orb, i) => (
        <motion.div
          key={i}
          className="orb"
          style={{
            width: orb.size,
            height: orb.size,
            left: orb.x,
            top: orb.y,
          }}
          animate={{
            y: [0, -40, 10, -20, 0],
            x: [0, 20, -15, 10, 0],
            scale: [1, 1.08, 0.95, 1.03, 1],
            opacity: [0.7, 1, 0.8, 1, 0.7],
          }}
          transition={{
            duration: orb.duration,
            delay: orb.delay,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
}
