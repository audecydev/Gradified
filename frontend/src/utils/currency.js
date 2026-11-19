const inrFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * Format a numeric amount in Indian Rupees (e.g. ₹20.00, ₹40,000.00).
 */
export const formatINR = (value) => {
  const num = Number(value || 0);
  if (Number.isNaN(num)) return inrFormatter.format(0);
  return inrFormatter.format(num);
};

