import { motion } from "framer-motion";
import { Zap } from "lucide-react";

export default function Header() {
  return (
    <motion.div
      className="header"
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
    >
      <motion.div
        className="logo"
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.1 }}
      >
        <Zap size={26} strokeWidth={2.5} />
      </motion.div>
      <h1>
        Lead <span>Enrichment</span> Pipeline
      </h1>
      <p>
        Upload a CSV of companies. Each one is enriched through live web data,
        news signals, and a 3-step AI chain.
      </p>
    </motion.div>
  );
}
