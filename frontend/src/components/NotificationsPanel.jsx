import { AlertTriangle, Info, Flame } from 'lucide-react'

// ── Malaysia timezone formatter ──────────────────────────────────────────────
const MYT_OPTIONS = {
  timeZone: 'Asia/Kuala_Lumpur',
  hour12: false,
  hour:   '2-digit',
  minute: '2-digit',
  second: '2-digit',
}
export const toMYT = (date = new Date()) =>
  date.toLocaleTimeString('en-MY', MYT_OPTIONS)

// ── Notification type metadata ───────────────────────────────────────────────
const TYPE_META = {
  critical: {
    bg:   'bg-red-500/10 border-red-500/30 shadow-[0_0_8px_rgba(239,68,68,0.15)]',
    text: 'text-red-100',
    icon: <Flame className="w-4 h-4 text-red-400 animate-pulse shrink-0" />,
  },
  warning: {
    bg:   'bg-amber-500/10 border-amber-500/30',
    text: 'text-amber-100',
    icon: <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />,
  },
  info: {
    bg:   'bg-slate-800/50 border-white/5',
    text: 'text-slate-200',
    icon: <Info className="w-4 h-4 text-emerald-400 shrink-0" />,
  },
}

export default function NotificationsPanel({ active, notifications = [] }) {
  if (!active || notifications.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-slate-600 border border-white/5 rounded-xl bg-black/20 h-full">
        <span className="font-mono text-xs uppercase tracking-widest">
          {active ? 'No alerts yet' : 'Deploy swarm to begin'}
        </span>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto space-y-2 pr-1 h-full
      [scrollbar-width:thin] [scrollbar-color:rgba(255,255,255,0.1)_transparent]
      hover:[scrollbar-color:rgba(255,255,255,0.2)_transparent]">
      {notifications.map((notif, index) => {
        const meta = TYPE_META[notif.type] || TYPE_META.info
        return (
          <div
            key={notif.id ?? index}
            className={`p-3 rounded-lg border transition-colors ${meta.bg} hover:brightness-110`}
          >
            <div className="flex gap-2 items-start">
              <div className="mt-0.5">{meta.icon}</div>
              <div className="flex-1 min-w-0">
                <div className="flex justify-between items-start gap-2">
                  <span className={`text-sm font-medium leading-snug ${meta.text}`}>
                    {notif.msg}
                  </span>
                  {/* Timestamp in Malaysia Time */}
                  <span className="text-[10px] text-slate-500 font-mono tracking-wider whitespace-nowrap shrink-0">
                    {notif.time}
                  </span>
                </div>
                {notif.drone_id && notif.drone_id !== 'ENVIRONMENT' && (
                  <span className="mt-0.5 text-[10px] text-slate-500 font-mono block">
                    {notif.drone_id}
                  </span>
                )}
                {notif.coords && (
                  <span className="mt-0.5 text-[10px] text-slate-500 font-mono block">
                    📍 {notif.coords}
                  </span>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
