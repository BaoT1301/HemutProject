import { motion } from "framer-motion";

const FOOTER_ITEMS = [
  {
    label: "Data Sources",
    value: "Company Website, Tavily Search, Wikipedia, Google News, GDELT",
  },
  {
    label: "AI Pipeline",
    value: "GPT-4o-mini, Structured Outputs, 3 chained calls, tenacity retry",
  },
  {
    label: "Output Fields",
    value:
      "Industry, ICP, Sales Angles, Risk Signals, Lead Score, News Summary",
  },
  {
    label: "Infrastructure",
    value: "SQLite cache (7d TTL), Concurrent processing (3x), Rate limiting",
  },
];

export default function FooterGrid() {
  return (
    <>
      <div className="footer-grid">
        {FOOTER_ITEMS.map((item, i) => (
          <motion.div
            key={item.label}
            className="footer-item"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 + i * 0.06, duration: 0.4 }}
          >
            <div className="footer-item-label">{item.label}</div>
            <div className="footer-item-value">{item.value}</div>
          </motion.div>
        ))}
      </div>
      <motion.div
        className="powered-by"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.6, duration: 0.5 }}
      >
        Built for <a href="https://hemut.com" target="_blank" rel="noopener noreferrer">Hemut</a>
      </motion.div>
    </>
  );
}
