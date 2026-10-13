// Offer wording reaches the chat from three sources: the templated copy, BigQuery-generated
// copy, and pre-generated BigQuery copy. They do not agree on how the price is written: it may
// be "₹50", "Rs 50", "Rs. 50", "Rs50" or "INR 50", and the word "for" may or may not sit in
// front of it ("for ₹50", "at ₹50", "are Rs 50 when bought together", "just Rs 50"). Live specs
// must therefore not depend on the word before the price or on the currency spelling, and the
// negative checks (price must not appear) must use this same pattern or they pass vacuously.
// The trailing \b keeps 500 and 5 from matching.
export const OFFER_PRICE_50 = /(?:₹|Rs\.?\s?|INR\s?)50\b/;

// The best-before disclosure, in English or Kannada. Case-insensitive because generated copy
// writes both "Best-before date" and "best before".
export const BEST_BEFORE = /Best[- ]before|ಬಳಕೆಗೆ/i;
