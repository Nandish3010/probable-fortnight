import { ChatPanel } from "../../components/ChatPanel";

export default function ChatPage() {
  return (
    <main className="page">
      <h2>Customer chat</h2>
      <p className="muted">Full-page version of the customer chat used in the landing hero. Switch customer below to see a different home store, language, or the holdout arm getting no offer.</p>
      <ChatPanel />
    </main>
  );
}
