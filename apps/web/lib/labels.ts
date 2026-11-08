// What users see for FINN's internal categories.

const CATEGORY: Record<string, string> = {
  results: "Results",
  "M&A": "Acquisition or merger",
  management_change: "Board or management",
  fund_raise: "Fund raise",
  pledging: "Promoter pledge",
  litigation: "Legal or regulatory",
  capex: "Capacity or capex",
  credit_rating: "Credit rating",
  insider_trading: "Insider trade",
  bonus_split: "Bonus or split",
  press_release: "Press release",
  dividend: "Dividend",
  earnings_call: "Earnings call",
  investor_meetings: "Investor meeting",
  agm_egm: "Shareholder meeting",
  postal_ballot: "Postal ballot",
  unclassified: "Other filing",
};

const STAGE: Record<string, string> = {
  "results:intimation": "Results date set",
  "results:presentation": "Results presentation",
  "results:newspaper_ad": "Results newspaper ad",
  "results:press_release": "Results press release",
  "earnings_call:transcript": "Call transcript",
  "earnings_call:recording": "Call recording",
  "earnings_call:notice": "Earnings call notice",
};

export function categoryLabel(category: string, stage?: string | null): string {
  return (stage && STAGE[`${category}:${stage}`]) || CATEGORY[category] || "Other filing";
}

export const ANOMALY: Record<string, string> = {
  volume_multiple: "Volume",
  price_move: "Price",
  sigma_move: "Unusual move",
  delivery_spike: "Delivery",
};
