import { ChatPanel } from "../../components/ChatPanel";

export default function ChatPage() {
  return (
    <main className="page">
      <h2>Chat as Meena</h2>
      <p className="muted">Full-page version of the customer chat used in the landing hero.</p>
      <ChatPanel />
    </main>
  );
}
