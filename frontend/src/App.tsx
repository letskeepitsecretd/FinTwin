"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Activity,
  Zap,
  Mail,
  CheckCircle2,
  AlertCircle,
  TrendingUp,
  Shield,
  Brain,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Transaction {
  id: string;
  customerName: string;
  amount: number;
  category: string;
  timestamp: string;
  isLifeEvent?: boolean;
}

interface AIDecision {
  id: string;
  customerId: string;
  customerName: string;
  city: string;
  eventType: string;
  signal: string;
  finalProducts: string[];
  reasoning: string;
  outreachBody: string;
  outreachSubject: string;
  wasRevised: boolean;
  priority: "high" | "medium" | "low";
  confidence: number;
  autoSent?: boolean;
}

type SendStatus = "idle" | "sending" | "sent" | "failed";

// ---------------------------------------------------------------------------
// Stat Card
// ---------------------------------------------------------------------------

const StatCard: React.FC<{
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color: string;
}> = ({ icon, label, value, color }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    className="bg-white rounded-xl p-4 shadow-sm border border-gray-100"
  >
    <div className="flex items-center gap-3">
      <div className={cn("p-2 rounded-lg", color)}>{icon}</div>
      <div>
        <p className="text-sm text-gray-600">{label}</p>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
      </div>
    </div>
  </motion.div>
);

// ---------------------------------------------------------------------------
// Transaction Row
// ---------------------------------------------------------------------------

const TransactionRow: React.FC<{ transaction: Transaction }> = ({
  transaction,
}) => (
  <motion.div
    initial={{ opacity: 0, x: -20 }}
    animate={{ opacity: 1, x: 0 }}
    className={cn(
      "bg-white rounded-lg p-4 border border-gray-100 mb-2",
      transaction.isLifeEvent && "border-l-4 border-l-[#D4A24C] shadow-md"
    )}
  >
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        {transaction.isLifeEvent && (
          <Zap className="w-4 h-4 text-[#D4A24C]" />
        )}
        <div>
          <p className="font-semibold text-gray-900">{transaction.customerName}</p>
          <div className="flex items-center gap-2 mt-1">
            <Badge variant="secondary" className="text-xs bg-gray-100 text-gray-700">
              {transaction.category}
            </Badge>
            <span className="text-xs text-gray-500">{transaction.timestamp}</span>
          </div>
        </div>
      </div>
      <p className="text-lg font-bold text-[#D4A24C]">
        ₹{transaction.amount.toLocaleString()}
      </p>
    </div>
  </motion.div>
);

// ---------------------------------------------------------------------------
// AI Decision Card
// ---------------------------------------------------------------------------

const priorityColors = {
  high: "bg-red-100 text-red-700 border-red-200",
  medium: "bg-amber-100 text-amber-700 border-amber-200",
  low: "bg-green-100 text-green-700 border-green-200",
};

const AIDecisionCard: React.FC<{
  decision: AIDecision;
  sendStatus: SendStatus;
  onSend: (decision: AIDecision) => void;
}> = ({ decision, sendStatus, onSend }) => {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="bg-white rounded-xl p-5 shadow-md border border-gray-100 mb-3"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <div>
          <p className="font-bold text-gray-900">{decision.customerName}</p>
          <p className="text-sm text-gray-500">{decision.city}</p>
        </div>
        <Badge className="bg-[#1e3a5f] text-white text-xs">{decision.eventType}</Badge>
      </div>

      {/* Signal */}
      <p className="text-sm text-gray-600 mb-3">{decision.signal}</p>

      {/* Products */}
      {decision.finalProducts.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {decision.finalProducts.map((p, i) => (
            <span key={i} className="text-xs bg-amber-50 text-amber-800 border border-amber-200 rounded-full px-2 py-0.5">
              {p}
            </span>
          ))}
        </div>
      )}

      {/* Reasoning (collapsed by default) */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-xs text-[#1e3a5f] font-semibold mb-2 hover:underline"
      >
        <Brain className="w-3 h-3" />
        {expanded ? "Hide reasoning" : "Show agent reasoning"}
      </button>

      {expanded && (
        <div className="bg-gray-50 rounded-lg p-3 mb-3 text-xs text-gray-700 leading-relaxed border border-gray-100">
          {decision.reasoning}
        </div>
      )}

      {/* Draft message */}
      {decision.outreachBody && (
        <div className="bg-blue-50 rounded-lg p-3 mb-3 border border-blue-100">
          {decision.outreachSubject && (
            <p className="text-xs font-semibold text-blue-800 mb-1">
              Subject: {decision.outreachSubject}
            </p>
          )}
          <p className="text-xs text-blue-900 leading-relaxed">{decision.outreachBody}</p>
        </div>
      )}

      {/* Compliance + Priority row */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1">
          {decision.wasRevised ? (
            <Shield className="w-4 h-4 text-amber-500" />
          ) : (
            <CheckCircle2 className="w-4 h-4 text-green-600" />
          )}
          <span className="text-xs text-gray-600">
            {decision.wasRevised ? "Compliance revised" : "Compliance verified"}
          </span>
        </div>
        <Badge className={cn("text-xs border", priorityColors[decision.priority] || priorityColors.medium)}>
          {decision.priority.toUpperCase()}
        </Badge>
      </div>

      {/* Send button */}
      {decision.autoSent ? (
        <div className="w-full bg-green-50 border border-green-200 rounded-lg px-4 py-2 flex items-center gap-2">
          <Zap className="w-4 h-4 text-green-600" />
          <span className="text-sm font-semibold text-green-700">⚡ Auto-Sent — High Priority</span>
        </div>
      ) : (
        <>
          {/* Editable draft for medium/low priority */}
          <div className="mb-3">
            <p className="text-xs font-semibold text-amber-700 mb-1">
              📝 Review & edit before sending
            </p>
            <textarea
              className="w-full text-xs text-gray-800 bg-gray-50 border border-gray-200 rounded-lg p-2 resize-none focus:outline-none focus:border-amber-400"
              rows={4}
              defaultValue={decision.outreachBody}
              onChange={(e) => {
                decision.outreachBody = e.target.value;
              }}
            />
          </div>
          <Button
            onClick={() => onSend(decision)}
            disabled={sendStatus === "sending" || sendStatus === "sent"}
            className={cn(
              "w-full font-semibold text-sm py-2",
              sendStatus === "sent"
                ? "bg-green-500 text-white cursor-not-allowed"
                : sendStatus === "sending"
                ? "bg-gray-400 text-white cursor-not-allowed"
                : sendStatus === "failed"
                ? "bg-red-500 text-white"
                : "bg-[#D4A24C] hover:bg-[#c49343] text-gray-900"
            )}
          >
            {sendStatus === "sent" ? "✓ Sent" : sendStatus === "sending" ? "Sending..." : sendStatus === "failed" ? "Retry" : "Approve & Send"}
          </Button>
        </>
      )}
    </motion.div>
  );
};

// ---------------------------------------------------------------------------
// Main Dashboard
// ---------------------------------------------------------------------------

const FinTwinDashboard: React.FC = () => {
  const [speed, setSpeed] = React.useState<number>(1);
  const [isActive, setIsActive] = React.useState<boolean>(false);
  const [transactions, setTransactions] = React.useState<Transaction[]>([]);
  const [aiDecisions, setAiDecisions] = React.useState<AIDecision[]>([]);
  const [stats, setStats] = React.useState({ transactions: 0, events: 0, emails: 0 });
  const [sendStatuses, setSendStatuses] = React.useState<Map<string, SendStatus>>(new Map());
  const wsRef = React.useRef<WebSocket | null>(null);
  const speeds = [1, 5, 10, 20];

  // Load existing runs from SQLite-backed API on mount
  React.useEffect(() => {
    fetch("http://localhost:8000/api/runs")
      .then(r => r.json())
      .then((runs: any[]) => {
        if (!Array.isArray(runs)) return;
        const decisions = runs.slice(0, 10).map(parseAgentRun);
        setAiDecisions(decisions);
        setStats(s => ({ ...s, events: decisions.length }));
      })
      .catch(() => console.log("FastAPI not connected yet"));
  }, []);

  // WebSocket — receive only, start/stop via REST
  React.useEffect(() => {
    if (!isActive) {
      wsRef.current?.close();
      return;
    }

    const ws = new WebSocket("ws://localhost:8000/ws");
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === "transaction") {
          const txn: Transaction = {
            id: data.id || Date.now().toString(),
            customerName: data.customer_name,
            amount: data.amount,
            category: data.category,
            timestamp: "just now",
            isLifeEvent: data.is_life_event || false,
          };
          setTransactions(prev => [txn, ...prev].slice(0, 20));
          setStats(s => ({ ...s, transactions: s.transactions + 1 }));
        } else if (data.type === "auto_sent") {
          setAiDecisions(prev => prev.map(d => 
            d.customerId === data.customer_id 
              ? { ...d, autoSent: true }
              : d
          ));
          setStats(s => ({ ...s, emails: s.emails + 1 }));
        } else if (data.type === "agent_decision" || data.customer_id) {
          const decision = parseAgentRun(data);
          setAiDecisions(prev => {
            const exists = prev.findIndex(d => d.customerId === decision.customerId);
            if (exists >= 0) {
              const updated = [...prev];
              updated[exists] = decision;
              return updated;
            }
            return [decision, ...prev].slice(0, 15);
          });
          setStats(s => ({ ...s, events: s.events + 1 }));
        }
      } catch (e) {
        console.error("WebSocket parse error:", e);
      }
    };

    ws.onerror = () => console.log("WebSocket error — is FastAPI running?");
    ws.onclose = () => {
      // Auto-reconnect after 3s if still active
      if (isActive) setTimeout(() => {}, 3000);
    };

    return () => ws.close();
  }, [isActive]);

  const parseAgentRun = (data: any): AIDecision => ({
    id: data.customer_id || Date.now().toString(),
    customerId: data.customer_id || Date.now().toString(),
    customerName: data.customer_name || "Unknown",
    city: data.city || "India",
    eventType: data.event_label || data.event_type || "Event",
    signal: data.signal || "",
    finalProducts: Array.isArray(data.final_products)
      ? data.final_products
      : data.recommended_products?.map((p: any) => p.name || p) || [],
    reasoning: data.reasoning || data.ai_reasoning || "",
    outreachBody: data.outreach?.body || "",
    outreachSubject: data.outreach?.subject || "",
    wasRevised: data.outreach?.was_revised || false,
    priority: (data.priority || "medium").toLowerCase() as "high" | "medium" | "low",
    confidence: data.confidence || 0.85,
  });

  const handleSendEmail = async (decision: AIDecision) => {
    setSendStatuses(prev => new Map(prev).set(decision.customerId, "sending"));
    try {
      const res = await fetch("http://localhost:8000/api/send-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to_email: "dev.1806raikwar21@gmail.com",
          customer_name: decision.customerName,
          event_type: decision.eventType,
          signal: decision.signal,
          recommended_products: decision.finalProducts.join(", "),
          subject: decision.outreachSubject || `SBI FinTwin — ${decision.eventType}`,
          body: decision.outreachBody,
        }),
      });
      if (res.ok) {
        setSendStatuses(prev => new Map(prev).set(decision.customerId, "sent"));
        setStats(s => ({ ...s, emails: s.emails + 1 }));
      } else {
        setSendStatuses(prev => new Map(prev).set(decision.customerId, "failed"));
      }
    } catch (e) {
      console.error("Email send failed:", e);
      setSendStatuses(prev => new Map(prev).set(decision.customerId, "failed"));
    }
  };

  const handleToggle = async () => {
    try {
      const endpoint = isActive
        ? "http://localhost:8000/api/feed/stop"
        : "http://localhost:8000/api/feed/start";
      await fetch(endpoint, { method: "POST" });
      if (!isActive) {
        // Also set speed
        await fetch("http://localhost:8000/api/feed/speed", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ speed }),
        });
      }
    } catch (e) {
      console.error("Failed to toggle feed:", e);
    }
    setIsActive(!isActive);
  };

  const handleSpeedChange = async (s: number) => {
    setSpeed(s);
    if (isActive) {
      try {
        await fetch("http://localhost:8000/api/feed/speed", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ speed: s }),
        });
      } catch (e) {
        console.error("Speed change failed:", e);
      }
    }
  };

  return (
    <div className="min-h-screen bg-[#0a1628] p-6">
      <div className="max-w-[1800px] mx-auto grid grid-cols-12 gap-6">
        {/* Left Sidebar */}
        <div className="col-span-3 space-y-6">
          <div>
            <h1 className="text-3xl font-bold text-[#D4A24C] mb-1">FinTwin</h1>
            <p className="text-sm text-white/80">Agentic AI · by SBI</p>
          </div>

          <div>
            <p className="text-sm text-white/70 mb-3">Simulation Speed</p>
            <div className="grid grid-cols-4 gap-2">
              {speeds.map((s) => (
                <button
                  key={s}
                  onClick={() => handleSpeedChange(s)}
                  className={cn(
                    "py-2 px-3 rounded-lg font-semibold text-sm transition-all",
                    speed === s
                      ? "bg-[#D4A24C] text-gray-900"
                      : "bg-transparent border-2 border-white/30 text-white hover:border-white/50"
                  )}
                >
                  {s}x
                </button>
              ))}
            </div>
          </div>

          <Button
            onClick={handleToggle}
            className="w-full bg-[#D4A24C] hover:bg-[#c49343] text-gray-900 font-bold py-6 rounded-xl"
          >
            {isActive ? "Stop Simulation" : "Start Simulation"}
          </Button>

          <div className="space-y-3">
            <StatCard
              icon={<Activity className="w-5 h-5 text-blue-600" />}
              label="Transactions Processed"
              value={stats.transactions.toLocaleString()}
              color="bg-blue-50"
            />
            <StatCard
              icon={<Zap className="w-5 h-5 text-amber-600" />}
              label="Events Detected"
              value={stats.events}
              color="bg-amber-50"
            />
            <StatCard
              icon={<Mail className="w-5 h-5 text-green-600" />}
              label="Emails Sent"
              value={stats.emails}
              color="bg-green-50"
            />
          </div>

          <div className="bg-white rounded-xl p-4 flex items-center gap-3">
            <div className={cn(
              "w-2 h-2 rounded-full transition-all",
              isActive ? "bg-green-500 animate-pulse" : "bg-gray-400"
            )} />
            <span className="text-sm font-semibold text-gray-900">
              {isActive ? "System Active" : "System Idle"}
            </span>
          </div>
        </div>

        {/* Center — Live Transactions */}
        <div className="col-span-5">
          <Card className="bg-white rounded-2xl p-6 h-full shadow-lg border-0">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-gray-900">Live Transaction Feed</h2>
              <TrendingUp className="w-6 h-6 text-[#D4A24C]" />
            </div>
            {transactions.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-64 text-gray-400">
                <AlertCircle className="w-12 h-12 mb-3 opacity-30" />
                <p>No transactions yet. Start the simulation.</p>
              </div>
            ) : (
              <div className="space-y-2 overflow-y-auto max-h-[calc(100vh-200px)]">
                <AnimatePresence>
                  {transactions.map((t) => (
                    <TransactionRow key={t.id} transaction={t} />
                  ))}
                </AnimatePresence>
              </div>
            )}
          </Card>
        </div>

        {/* Right — AI Decisions */}
        <div className="col-span-4">
          <Card className="bg-white rounded-2xl p-6 h-full shadow-lg border-0">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-gray-900">AI Agent Decisions</h2>
              <Brain className="w-6 h-6 text-[#D4A24C]" />
            </div>
            {aiDecisions.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-64 text-gray-400">
                <Zap className="w-12 h-12 mb-3 opacity-30" />
                <p>No events detected yet. AI is monitoring.</p>
              </div>
            ) : (
              <div className="space-y-3 overflow-y-auto max-h-[calc(100vh-200px)]">
                <AnimatePresence>
                  {aiDecisions.map((d) => (
                    <AIDecisionCard
                      key={d.id}
                      decision={d}
                      sendStatus={sendStatuses.get(d.customerId) || "idle"}
                      onSend={handleSendEmail}
                    />
                  ))}
                </AnimatePresence>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
};

export default function Demo() {
  return <FinTwinDashboard />;
}
