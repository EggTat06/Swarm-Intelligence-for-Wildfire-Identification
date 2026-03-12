import { AlertTriangle, Info, Flame } from 'lucide-react'

const MOCK_NOTIFICATIONS = [
  { id: 1, type: 'critical', time: '14:02:45', msg: 'YOLOv8 CONFIRMED FIRE: Drone-7x2', coords: '45.122, -112.451' },
  { id: 2, type: 'info', time: '14:00:12', msg: 'Drone-7x2 altered heading (DSP)', coords: null },
  { id: 3, type: 'warning', time: '13:58:33', msg: 'Heat signature detected. Verifying...', coords: '45.120, -112.449' },
  { id: 4, type: 'info', time: '13:55:00', msg: 'Swarm deployment initialized', coords: null },
]

export default function NotificationsPanel({ active }) {
  if (!active) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-slate-600 border border-white/5 rounded-xl bg-black/20">
        <span className="font-mono text-xs uppercase tracking-widest">Logs Empty</span>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto space-y-3 pr-2 custom-scrollbar">
      {MOCK_NOTIFICATIONS.map((notif) => (
        <div
          key={notif.id}
          className={`p-3 rounded-lg border ${
            notif.type === 'critical' ? 'bg-red-500/10 border-red-500/30 shadow-[0_0_10px_rgba(239,68,68,0.1)]' :
            notif.type === 'warning' ? 'bg-amber-500/10 border-amber-500/30' :
            'bg-slate-800/50 border-white/5'
          } hover:bg-slate-800 transition-colors group cursor-default`}
        >
          <div className="flex gap-3">
            <div className="mt-0.5">
              {notif.type === 'critical' && <Flame className="w-4 h-4 text-red-500 animate-pulse" />}
              {notif.type === 'warning' && <AlertTriangle className="w-4 h-4 text-amber-500" />}
              {notif.type === 'info' && <Info className="w-4 h-4 text-emerald-500" />}
            </div>
            <div className="flex-1">
              <div className="flex justify-between items-start">
                <span className={`text-sm font-medium ${
                  notif.type === 'critical' ? 'text-red-100' : 'text-slate-200'
                }`}>
                  {notif.msg}
                </span>
                <span className="text-[10px] text-slate-500 font-mono tracking-wider ml-2 whitespace-nowrap">
                  {notif.time}
                </span>
              </div>
              {notif.coords && (
                <div className="mt-1 text-xs text-slate-400 font-mono">
                  LOC: {notif.coords}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
