import { useState, useEffect, useRef, useCallback } from 'react';
import { ShieldAlert, Activity, Wifi, Settings, Plus, Minus, Flame, Radio } from 'lucide-react';
import MapGrid from './components/MapGrid';
import NotificationsPanel from './components/NotificationsPanel';
import DroneFootage from './components/DroneFootage';

// Unique notification factory — timestamps in Malaysia Time (UTC+8)
let notifIdCounter = 0;
const MYT = {
  timeZone: 'Asia/Kuala_Lumpur', hour12: false,
  hour: '2-digit', minute: '2-digit', second: '2-digit'
};
const makeNotif = (type, msg, drone_id = null, coords = null) => ({
  id: ++notifIdCounter,
  type,          // 'critical' | 'warning' | 'info'
  msg,
  drone_id,
  coords,
  time: new Date().toLocaleTimeString('en-MY', MYT),
});

function App() {
  const [missionActive, setMissionActive] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [envState, setEnvState] = useState(null);
  const [drones, setDrones] = useState({});
  const [identifiedFires, setIdentifiedFires] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [selectedDroneId, setSelectedDroneId] = useState(null);
  const [missionResults, setMissionResults] = useState(null);
  const [showResults, setShowResults] = useState(false);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  const wsRef = useRef(null);

  const addNotif = useCallback((type, msg, drone_id = null, coords = null) => {
    setNotifications(prev => [makeNotif(type, msg, drone_id, coords), ...prev].slice(0, 100));
  }, []);

  // ── WebSocket ─────────────────────────────────────────────────────────
  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket('ws://localhost:8000/ws');
      wsRef.current = ws;
      ws.onopen = () => setIsConnected(true);
      ws.onclose = () => { setIsConnected(false); setTimeout(connect, 3000); };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'environment_state') {
            setEnvState(data);

          } else if (data.type === 'swarm_telemetry') {
            const map = {};
            (data.drones || []).forEach(d => { map[d.drone_id] = d; });
            setDrones(map);
            setIdentifiedFires(data.discovered_fires || []);

          } else if (data.type === 'drone_notification') {
            // Determine category from message text
            const msg = data.message || '';
            const isFireAlert = msg.toLowerCase().includes('fire') ||
              msg.toLowerCase().includes('wildfire');
            const isArrival = msg.toLowerCase().includes('reached');
            const type = isFireAlert ? 'critical' : isArrival ? 'warning' : 'info';
            addNotif(type, msg, data.drone_id);
          } else if (data.type === 'mission_report') {
            setMissionResults(data);
            addNotif('info', 'Mission report received. Click the chart icon to view results.');
          } else if (data.type === 'MISSION_CLEARED') {
            setMissionActive(false);
            addNotif('info', 'All drones have returned to base. Mission cleared.');
          }
        } catch (err) { console.error('WS parse error:', err); }
      };
    };
    connect();
    return () => wsRef.current?.close();
  }, [addNotif]);

  // ── Actions ───────────────────────────────────────────────────────────
  const wsSend = useCallback((payload) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  }, []);

  const handleToggleMission = () => {
    if (missionActive) {
      // abort pulse
      wsSend({ type: 'command', command: 'ABORT' });
      addNotif('info', 'Mission aborted. Drones returning to base. Map will close once all drones home.');
    } else {
      // deploy
      setMissionActive(true);
      wsSend({ type: 'command', command: 'DEPLOY' });
      addNotif('info', 'Swarm deployed. 10 UAVs initializing from base.');
    }
  };

  const handleSwarmControl = (action) => {
    let payload = { type: 'swarm_control', action };
    if (action === 'remove' && selectedDroneId) {
      payload.drone_id = selectedDroneId;
    }
    wsSend(payload);
    addNotif('info', action === 'add' ? 'Drone added to swarm from base.' : 'Drone removed from swarm.');
  };

  const handleDroneSelect = (id) => setSelectedDroneId(prev => prev === id ? null : id);

  const handleMapCommand = (droneId, worldX, worldY) => {
    wsSend({
      type: 'swarm_control', action: 'command',
      drone_id: droneId, target_x: worldX, target_y: worldY
    });
    addNotif('warning',
      `${droneId} commanded to (${worldX.toFixed(0)}, ${worldY.toFixed(0)}).`,
      droneId,
      `${(worldX / 1000).toFixed(1)}km, ${(worldY / 1000).toFixed(1)}km`
    );
  };

  const handleReleaseDrone = (droneId) => {
    wsSend({ type: 'swarm_control', action: 'release', drone_id: droneId });
    setSelectedDroneId(null);
    addNotif('info', `${droneId} released → resuming autonomous DSP patrol.`, droneId);
  };

  const handleResetMap = () => {
    if (missionActive) return;
    wsSend({ type: 'swarm_control', action: 'RESET' });
    setEnvState(null);
    setDrones({});
    setIdentifiedFires([]);
    setNotifications([]);
    addNotif('warning', 'Environment reset. Regenerating map layout and re-seeding fires.');
  };

  const fetchHistory = async () => {
    try {
      const res = await fetch('http://localhost:8000/history/missions');
      const data = await res.json();
      setHistory(data);
      setShowHistory(true);
    } catch (err) {
      console.error('Failed to fetch mission history:', err);
    }
  };

  const handleViewHistoricalMission = (m) => {
    const results = {
      fires_identified: m.fires_identified || 0,
      area_coverage_pct: m.swarm_parameters?.coverage || 0,
      duration: (new Date(m.end_time) - new Date(m.start_time)) / 1000,
      first_detection_seconds: m.time_to_first_detection,
      drones_deployed: m.swarm_parameters?.drones || 0,
      drone_paths: m.drone_paths
    };
    setMissionResults(results);
    setShowHistory(false);
    setShowResults(true);
  };

  // ── Derived ───────────────────────────────────────────────────────────
  const activeDrones = Object.values(drones);
  const totalCaCells = envState?.ca_cells?.length || 0;
  const identifiedCount = identifiedFires.length;
  const selectedDrone = drones[selectedDroneId];

  return (
    <div className="flex flex-col h-screen bg-dark text-slate-100 font-sans overflow-hidden">
      {/* ── Navbar ── */}
      <header className="h-16 border-b border-white/10 flex items-center justify-between px-6 bg-card/80 backdrop-blur-md z-10 shrink-0">
        <div className="flex items-center gap-3">
          <ShieldAlert className="text-primary w-6 h-6" />
          <h1 className="text-xl font-bold tracking-wider uppercase">Swarm Commander</h1>
        </div>

        <div className="flex items-center gap-5">
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Wifi className={`w-4 h-4 ${isConnected ? 'text-emerald-400' : 'text-red-500'}`} />
            <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>

          <div className="flex items-center gap-2 border-x border-white/10 px-4">
            <button onClick={() => handleSwarmControl('remove')} className="p-1 hover:bg-white/10 rounded">
              <Minus className="w-4 h-4 text-slate-300" />
            </button>
            <span className="font-mono text-sm w-14 text-center text-emerald-400">
              {activeDrones.length} UAVs
            </span>
            <button onClick={() => handleSwarmControl('add')} className="p-1 hover:bg-white/10 rounded">
              <Plus className="w-4 h-4 text-slate-300" />
            </button>
          </div>

          <button onClick={handleResetMap} disabled={missionActive}
            className={`p-2 rounded-full transition ${missionActive ? 'text-slate-600' : 'hover:bg-white/5 text-slate-400'}`}
            title="Generate New Map">
            <Radio className="w-5 h-5" />
          </button>

          <button onClick={handleToggleMission}
            className={`px-6 py-2 rounded-full font-semibold transition-all duration-300
              ${missionActive
                ? 'bg-red-500 hover:bg-red-600 text-white shadow-[0_0_15px_rgba(239,68,68,0.5)]'
                : 'bg-primary hover:bg-orange-600 text-white shadow-[0_0_15px_rgba(255,69,0,0.5)]'}`}>
            {missionActive ? 'ABORT MISSION' : 'DEPLOY SWARM'}
          </button>

          <button onClick={fetchHistory} className="p-2 hover:bg-white/5 rounded-full transition text-slate-400" title="Mission History">
            <Activity className="w-5 h-5" />
          </button>

          {missionResults && (
            <button onClick={() => setShowResults(true)} className="p-2 hover:bg-white/5 rounded-full transition text-primary animate-pulse" title="View Latest Mission Report">
              <Flame className="w-5 h-5" />
            </button>
          )}

          <button className="p-2 hover:bg-white/5 rounded-full transition text-slate-400">
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* ── Main ── */}
      <main className="flex-1 flex overflow-hidden min-h-0">

        {/* 3D Map */}
        <section className="flex-1 relative bg-dark">
          <MapGrid
            active={missionActive}
            envState={envState}
            drones={drones}
            identifiedFires={identifiedFires}
            selectedDroneId={selectedDroneId}
            onDroneSelect={handleDroneSelect}
            onMapCommand={handleMapCommand}
            missionResults={missionResults}
            onShowResults={() => setShowResults(true)}
          />

          {/* Stats overlay */}
          <div className="absolute top-4 left-4 p-4 rounded-xl bg-card/80 backdrop-blur border border-white/5 shadow-2xl space-y-3 z-10">
            <div className="flex items-center gap-2 text-sm text-slate-400 font-medium">
              <Activity className="w-4 h-4 text-emerald-400" /> SWARM STATUS
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div><p className="text-xs text-slate-500">Active Drones</p>
                <p className="text-xl font-bold font-mono">{activeDrones.length}</p></div>
              <div><p className="text-xs text-slate-500">Fire Detection</p>
                <p className="text-xl font-bold font-mono text-amber-400">
                  {identifiedCount} / {totalCaCells}
                </p></div>
            </div>
            {envState && (
              <div className="pt-2 mt-2 border-t border-white/10">
                <p className="text-xs text-slate-500 flex items-center gap-1">
                  <Flame className="w-3 h-3 text-red-500" /> Active Fire Cells
                </p>
                <p className="text-xs font-mono text-slate-300 mt-1">
                  Wind {envState.wind?.speed}m/s @ {envState.wind?.direction}°
                </p>
              </div>
            )}
          </div>

          {/* Drone HUD */}
          {selectedDrone && (
            <div className="absolute top-4 right-4 w-64 p-4 rounded-xl bg-card/90 backdrop-blur border border-purple-500/40 shadow-2xl z-10 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-purple-300 font-mono text-xs font-bold uppercase tracking-wider">
                  {selectedDrone.drone_id}
                </span>
                <button onClick={() => setSelectedDroneId(null)}
                  className="text-slate-500 hover:text-white text-xs">✕</button>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-white/5 rounded p-2">
                  <p className="text-slate-500">Battery</p>
                  <p className={`font-mono font-bold ${selectedDrone.battery > 20 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {selectedDrone.battery?.toFixed(1)}%
                  </p>
                </div>
                <div className="bg-white/5 rounded p-2">
                  <p className="text-slate-500">Speed</p>
                  <p className="font-mono font-bold text-sky-300">{selectedDrone.v?.toFixed(0)} m/s</p>
                </div>
                <div className="bg-white/5 rounded p-2">
                  <p className="text-slate-500">Heading</p>
                  <p className="font-mono font-bold text-slate-200">
                    {(selectedDrone.heading * 180 / Math.PI).toFixed(1)}°
                  </p>
                </div>
                <div className="bg-white/5 rounded p-2">
                  <p className="text-slate-500">State</p>
                  <p className={`font-mono font-bold text-xs truncate
                    ${['COMMANDED', 'COMMANDED_WALK'].includes(selectedDrone.state)
                      ? 'text-orange-400' : 'text-purple-400'}`}>
                    {selectedDrone.state}
                  </p>
                </div>
              </div>
              {['COMMANDED', 'COMMANDED_WALK'].includes(selectedDrone.state) && (
                <button onClick={() => handleReleaseDrone(selectedDroneId)}
                  className="w-full py-2 rounded bg-orange-500/20 hover:bg-orange-500/40 text-orange-300 text-xs font-semibold border border-orange-500/30 transition">
                  Release Drone → Auto DSP
                </button>
              )}
              <p className="text-slate-600 text-xs italic">Click map to command drone</p>
            </div>
          )}
        </section>

        {/* Right Panel */}
        <aside className="w-[400px] bg-card border-l border-white/5 flex flex-col z-10 shadow-[-10px_0_30px_rgba(0,0,0,0.5)]">
          <div className="h-[35%] border-b border-white/5 relative p-4 pb-0 flex flex-col">
            <h2 className="text-sm font-semibold tracking-widest text-slate-400 mb-3 uppercase">
              Optical Feed (YOLOv8)
            </h2>
            <div className="flex-1 mb-4 rounded-xl overflow-hidden shadow-inner border border-white/10">
              <DroneFootage active={missionActive} />
            </div>
          </div>

          {/* Alert Log — single unified panel, no mock data */}
          <div className="flex-1 flex flex-col p-4 overflow-hidden min-h-0">
            <div className="flex items-center justify-between mb-3 shrink-0">
              <span className="text-sm font-semibold tracking-widest text-slate-400 uppercase flex items-center gap-1">
                <Radio className="w-3 h-3" /> Alert Log
              </span>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-slate-600">{notifications.length} events</span>
                <span className="bg-red-500/20 text-red-400 px-2 py-0.5 rounded text-xs">Live</span>
              </div>
            </div>
            <div className="flex-1 overflow-hidden min-h-0">
              <NotificationsPanel active={missionActive} notifications={notifications} />
            </div>
          </div>
        </aside>
      </main>

      {/* ── Mission Results Modal ── */}
      {showResults && missionResults && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-card border border-white/10 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden">
            <div className="bg-primary/20 p-6 border-b border-white/5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <ShieldAlert className="text-primary w-8 h-8" />
                <h2 className="text-2xl font-bold uppercase tracking-tight">Mission After-Action Report</h2>
              </div>
              <button onClick={() => setShowResults(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>

            <div className="p-8 space-y-6">
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-1">
                  <p className="text-xs text-slate-500 uppercase tracking-widest font-semibold">Fire Detection</p>
                  <p className="text-3xl font-bold font-mono text-primary">{missionResults.fires_identified}</p>
                  <p className="text-xs text-slate-400 italic">Discovered by YOLOv8</p>
                </div>
                <div className="space-y-1">
                  <p className="text-xs text-slate-500 uppercase tracking-widest font-semibold">Area Coverage</p>
                  <p className="text-3xl font-bold font-mono text-emerald-400">{missionResults.area_coverage_pct}%</p>
                  <p className="text-xs text-slate-400 italic">Unique 500m cells scanned</p>
                </div>
                <div className="space-y-1">
                  <p className="text-xs text-slate-500 uppercase tracking-widest font-semibold">Mission Time</p>
                  <p className="text-3xl font-bold font-mono text-sky-400">{missionResults.duration?.toFixed(1)}s</p>
                  <p className="text-xs text-slate-400 italic">Total simulation seconds</p>
                </div>
                <div className="space-y-1">
                  <p className="text-xs text-slate-500 uppercase tracking-widest font-semibold">First Detection</p>
                  <p className="text-3xl font-bold font-mono text-amber-400">
                    {missionResults.first_detection_seconds ? `${missionResults.first_detection_seconds}s` : 'N/A'}
                  </p>
                  <p className="text-xs text-slate-400 italic">Time to initial contact</p>
                </div>
              </div>

              <div className="bg-white/5 rounded-xl p-4 border border-white/5">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-slate-300 uppercase tracking-wider">Resources Utilized</span>
                  <span className="text-emerald-400 font-mono text-sm">{missionResults.drones_deployed} UAVs</span>
                </div>
                <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden">
                  <div className="bg-primary h-full rounded-full" style={{ width: '100%' }}></div>
                </div>
              </div>

              <button onClick={() => setShowResults(false)}
                className="w-full py-4 bg-primary hover:bg-orange-600 text-white rounded-xl font-bold text-lg transition-all shadow-xl">
                DISMISS REPORT
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Mission History Modal ── */}
      {showHistory && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/90 backdrop-blur-md p-4">
          <div className="bg-card border border-white/10 rounded-2xl w-full max-w-4xl max-h-[80vh] shadow-2xl overflow-hidden flex flex-col">
            <div className="p-6 border-b border-white/5 flex items-center justify-between">
              <h2 className="text-xl font-bold uppercase tracking-widest flex items-center gap-3">
                <Activity className="text-emerald-400" /> Mission History Log
              </h2>
              <button onClick={() => setShowHistory(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>
            <div className="flex-1 overflow-y-auto p-6">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="text-left text-xs text-slate-500 uppercase tracking-widest border-b border-white/5">
                    <th className="pb-4 font-semibold">Start Time</th>
                    <th className="pb-4 font-semibold">Duration</th>
                    <th className="pb-4 font-semibold">Detection</th>
                    <th className="pb-4 font-semibold">Result</th>
                    <th className="pb-4 font-semibold">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {history.map(m => (
                    <tr key={m.mission_id} className="text-sm hover:bg-white/5 transition">
                      <td className="py-4 text-slate-300 font-mono">
                        {new Date(m.start_time).toLocaleString('en-MY', MYT)}
                      </td>
                      <td className="py-4 text-slate-400 font-mono">
                        {((new Date(m.end_time) - new Date(m.start_time)) / 1000).toFixed(0)}s
                      </td>
                      <td className="py-4 text-amber-400 font-mono">
                        {m.time_to_first_detection ? `${m.time_to_first_detection}s` : '-'}
                      </td>
                      <td className="py-4">
                        <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase
                          ${m.success ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                          {m.success ? 'Success' : 'Active/Fail'}
                        </span>
                      </td>
                      <td className="py-4">
                        <button
                          onClick={() => handleViewHistoricalMission(m)}
                          className="text-primary hover:text-orange-400 text-xs font-semibold underline underline-offset-4"
                        >
                          View Analysis
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {history.length === 0 && (
                <div className="py-20 text-center text-slate-600 italic">No missions recorded in database.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
