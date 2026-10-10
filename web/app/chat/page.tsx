import type { Metadata } from "next";
import { ChatPanel } from "../../components/ChatPanel";

export const metadata: Metadata = {
  title: "Chat | Taal",
  description: "Chat as a Taal customer and see the offer the agent sends, in the customer's own language.",
};

export default function ChatPage() {
  return (
    <main id="main-content" tabIndex={-1} className="page">
      <h1>Customer chat</h1>
      <p className="muted">Full-page version of the customer chat used in the landing hero. Switch customer below to see a different home store, language, or the holdout arm getting no offer.</p>
      <ChatPanel />
    </main>
  );
}
