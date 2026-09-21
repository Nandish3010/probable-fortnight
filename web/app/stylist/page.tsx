import { ChatPanel } from "../../components/ChatPanel";

export default function StylistPage() {
  return (
    <main className="page">
      <h1 className="visually-hidden">Taal</h1>
      <h2>Style assistant</h2>
      <p className="muted">
        Ask what goes with a piece of clothing, or show a photo. Pairings come from a deterministic
        colour wheel and what is actually in stock at your store -- Gemini only decides how to talk
        about the look. <a href="/trends">See what people are asking for →</a>
      </p>
      <ChatPanel
        specialist="stylist"
        title="Style for"
        initialMessage="What goes with a mustard yellow kurta?"
        suggestedChip="Show me navy T-shirts"
      />
    </main>
  );
}
