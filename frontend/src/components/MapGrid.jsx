import { useRef, useEffect, useState, useCallback, useMemo } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Environment } from '@react-three/drei'
import * as THREE from 'three'

// 100km world → 200 Three.js units wide. 1 Three.js unit = 500m.
const SCALE = 500.0

// Cell state → color mapping
const STATE_COLORS = {
  1: '#ffcc00',   // Early burn – yellow
  2: '#ff3300',   // Full burn  – red
  3: '#8b1a1a',   // Extinguish – dark red
  4: '#222222',   // Ash        – dark grey
}

// ─────────────────────────────────────────────
// CA Cell quad (flat box on ground plane)
// ─────────────────────────────────────────────
function CaCell({ cell }) {
  const color = STATE_COLORS[cell.state] || '#ff3300'
  const cellSize = 500 / SCALE   // 500m in Three.js units
  const ref = useRef()

  useFrame(({ clock }) => {
    if (ref.current && cell.state === 2) {
      ref.current.scale.y = 1 + Math.sin(clock.getElapsedTime() * 12 + cell.i) * 0.2
    }
  })

  return (
    <group ref={ref} position={[cell.x / SCALE, cell.state === 2 ? 0.3 : 0.1, cell.y / SCALE]}>
      <mesh castShadow>
        <boxGeometry args={[cellSize * 0.9, cell.state === 2 ? 0.6 : 0.2, cellSize * 0.9]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={cell.state === 2 ? 1.5 : 0.5} />
      </mesh>
      {cell.state <= 2 && (
        <pointLight color={color} intensity={cell.state === 2 ? 2 : 0.5} distance={8} />
      )}
    </group>
  )
}

// ─────────────────────────────────────────────
// Fog of war – explored circles (2D disc on ground)
// ─────────────────────────────────────────────
function ExploredCircles({ exploredCells, gridOffset }) {
  const radius = 6000 / SCALE
  return (
    <group position={[-gridOffset, 0.02, -gridOffset]}>
      {Array.from(exploredCells).map(key => {
        const [x, y] = key.split('|').map(Number)
        return (
          <mesh key={key} position={[x, 0, y]} rotation={[-Math.PI / 2, 0, 0]}>
            <circleGeometry args={[radius, 24]} />
            <meshBasicMaterial color="#00ffcc" transparent opacity={0.06} />
          </mesh>
        )
      })}
    </group>
  )
}

// ─────────────────────────────────────────────
// Drone Path component (connected lines)
// ─────────────────────────────────────────────
function DronePath({ path, color }) {
  const points = useMemo(() =>
    path.map(p => new THREE.Vector3(p[0] / SCALE, 1.0, p[1] / SCALE)),
    [path]
  )

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry().setFromPoints(points)
    return geo
  }, [points])

  return (
    <line geometry={geometry}>
      <lineBasicMaterial attach="material" color={color} linewidth={2} transparent opacity={0.6} />
    </line>
  )
}

// ─────────────────────────────────────────────
// Drone component
// ─────────────────────────────────────────────
function Drone({ pose, isSelected, onSelect }) {
  const groupRef = useRef()
  const dspRef = useRef()
  const targetPos = useRef(new THREE.Vector3(pose.x / SCALE, (pose.alt || 90) / 30, pose.y / SCALE))
  const dspPos = useRef(new THREE.Vector3((pose.dsp_x ?? pose.x) / SCALE, 1.5, (pose.dsp_y ?? pose.y) / SCALE))

  useEffect(() => {
    targetPos.current.set(pose.x / SCALE, (pose.alt || 90) / 30, pose.y / SCALE)
    if (pose.dsp_x != null) dspPos.current.set(pose.dsp_x / SCALE, 1.5, pose.dsp_y / SCALE)
  }, [pose])

  useFrame(({ clock }) => {
    if (groupRef.current) groupRef.current.position.lerp(targetPos.current, 0.12)
    if (dspRef.current) {
      dspRef.current.position.lerp(dspPos.current, 0.08)
      dspRef.current.rotation.y = clock.getElapsedTime() * 1.5
    }
  })

  const droneColor = isSelected
    ? (pose.state === 'COMMANDED' || pose.state === 'COMMANDED_WALK' ? '#ff8c00' : '#a855f7')
    : '#00ffcc'

  return (
    <group>
      {/* Drone body */}
      <group ref={groupRef}>
        <mesh castShadow onClick={(e) => { e.stopPropagation(); onSelect(pose.drone_id) }}
          onPointerOver={(e) => { e.stopPropagation(); document.body.style.cursor = 'pointer' }}
          onPointerOut={() => { document.body.style.cursor = 'auto' }}>
          <sphereGeometry args={[isSelected ? 1.1 : 0.8, 16, 16]} />
          <meshStandardMaterial color={droneColor} emissive={droneColor} emissiveIntensity={2.5} />
        </mesh>
        {/* 6km sensor range ring */}
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.3, 0]}>
          <ringGeometry args={[6000 / SCALE - 0.15, 6000 / SCALE, 48]} />
          <meshBasicMaterial color={droneColor} transparent opacity={isSelected ? 0.5 : 0.2} side={THREE.DoubleSide} />
        </mesh>
        {isSelected && (
          <pointLight color={droneColor} intensity={3} distance={15} />
        )}
      </group>
      {/* DSP target point (always visible, more prominent when selected) */}
      {pose.dsp_x != null && (
        <group ref={dspRef}>
          <mesh>
            <octahedronGeometry args={[isSelected ? 2.5 : 1.2, 0]} />
            <meshStandardMaterial color="#a855f7" emissive="#a855f7" wireframe
              emissiveIntensity={2} transparent opacity={isSelected ? 0.9 : 0.4} />
          </mesh>
          {isSelected && (
            <>
              {/* Wireframe circle showing DSP area of influence */}
              <mesh rotation={[-Math.PI / 2, 0, 0]}>
                <ringGeometry args={[10, 12, 48]} />
                <meshBasicMaterial color="#a855f7" transparent opacity={0.3} side={THREE.DoubleSide} />
              </mesh>
              <pointLight color="#a855f7" intensity={1} distance={20} />
            </>
          )}
        </group>
      )}

      {/* Commanded Target indicator */}
      {(pose.state === 'COMMANDED' || pose.state === 'COMMANDED_WALK') && pose.commanded_target_x != null && (
        <group position={[pose.commanded_target_x / SCALE, 0.5, pose.commanded_target_y / SCALE]}>
          <group ref={(ref) => {
            if (ref) {

            }
          }} />
          <CommandArrow targetX={pose.commanded_target_x} targetY={pose.commanded_target_y} />
        </group>
      )}
    </group>
  )
}

// ─────────────────────────────────────────────
// Commanded Target Arrow
// ─────────────────────────────────────────────
function CommandArrow({ targetX, targetY }) {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (ref.current) {
      ref.current.rotation.y = clock.getElapsedTime() * 4.0
    }
  })

  return (
    <group ref={ref}>
      {/* Square outline reticle */}
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[2.5, 3.5, 4, 1]} />
        <meshBasicMaterial color="#ff0044" transparent opacity={0.9} side={THREE.DoubleSide} />
      </mesh>
      {/* 4 inward-pointing triangles */}
      <mesh position={[0, 0, -3.5]} rotation={[-Math.PI / 2, 0, 0]}>
        <coneGeometry args={[1.5, 3, 3]} />
        <meshBasicMaterial color="#ff0044" />
      </mesh>
      <mesh position={[0, 0, 3.5]} rotation={[-Math.PI / 2, 0, Math.PI]}>
        <coneGeometry args={[1.5, 3, 3]} />
        <meshBasicMaterial color="#ff0044" />
      </mesh>
      <mesh position={[3.5, 0, 0]} rotation={[-Math.PI / 2, 0, -Math.PI / 2]}>
        <coneGeometry args={[1.5, 3, 3]} />
        <meshBasicMaterial color="#ff0044" />
      </mesh>
      <mesh position={[-3.5, 0, 0]} rotation={[-Math.PI / 2, 0, Math.PI / 2]}>
        <coneGeometry args={[1.5, 3, 3]} />
        <meshBasicMaterial color="#ff0044" />
      </mesh>
      <pointLight color="#ff0044" intensity={2} distance={20} position={[0, 2, 0]} />
    </group>
  )
}

// ─────────────────────────────────────────────
// Static entity components
// ─────────────────────────────────────────────
function Factory({ entity }) {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (ref.current) ref.current.intensity = 1.5 + Math.sin(clock.getElapsedTime() * 10) * 0.5
  })
  return (
    <group position={[entity.x / SCALE, 0, entity.y / SCALE]}>
      <mesh castShadow position={[0, 1, 0]}>
        <boxGeometry args={[entity.size / SCALE, 2, entity.size / SCALE]} />
        <meshStandardMaterial color="#4a4a4a" roughness={0.9} />
      </mesh>
      <pointLight ref={ref} position={[0, 3, 0]} color="#ff4500" distance={8} />
    </group>
  )
}
function Building({ entity }) {
  const h = entity.height / 100
  return (
    <mesh castShadow position={[entity.x / SCALE, h / 2, entity.y / SCALE]}>
      <boxGeometry args={[entity.size / SCALE, h, entity.size / SCALE]} />
      <meshStandardMaterial color="#2e3b4e" roughness={0.7} />
    </mesh>
  )
}
function Lake({ entity }) {
  return (
    <mesh position={[entity.x / SCALE, 0.05, entity.y / SCALE]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[entity.size / SCALE, entity.size / SCALE]} />
      <meshStandardMaterial color="#0255adff" transparent opacity={0.7} roughness={0.1} />
    </mesh>
  )
}
function Forest({ entity }) {
  return (
    <mesh castShadow position={[entity.x / SCALE, 0.7, entity.y / SCALE]}>
      <coneGeometry args={[entity.size / (SCALE * 1.8), 2, 8]} />
      <meshStandardMaterial color="#1e5235" roughness={0.8} />
    </mesh>
  )
}

// ─────────────────────────────────────────────
// Left-click command plane (invisible intercept)
// Only active when a drone is selected.
// ─────────────────────────────────────────────
function CommandPlane({ selectedDroneId, onMapCommand, gridOffset }) {
  const handleClick = useCallback((e) => {
    e.stopPropagation()
    if (!selectedDroneId) return
    const point = e.point
    // Convert Three.js space → world metres
    const worldX = (point.x + gridOffset) * SCALE
    const worldY = (point.z + gridOffset) * SCALE
    onMapCommand(selectedDroneId, worldX, worldY)
  }, [selectedDroneId, onMapCommand, gridOffset])

  // When no drone is selected, don't intercept clicks at all
  if (!selectedDroneId) return null

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]} onClick={handleClick}>
      <planeGeometry args={[2000, 2000]} />
      <meshBasicMaterial transparent opacity={0} />
    </mesh>
  )
}

// ─────────────────────────────────────────────
// World — all static entities + CA + home ring
// ─────────────────────────────────────────────
function World({ envState, identifiedFires, exploredCells, selectedDroneId, onMapCommand }) {
  if (!envState) return null

  const gw = envState.grid?.width || 100_000
  const gh = envState.grid?.height || 100_000
  const ox = gw / (2 * SCALE)
  const oy = gh / (2 * SCALE)

  return (
    <group position={[-ox, 0, -oy]}>
      {/* Ground - centered at (ox, oy) to cover range [0, gw] */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow position={[ox, 0.0, oy]}>
        <planeGeometry args={[gw / SCALE, gh / SCALE]} />
        <meshStandardMaterial color="#9b7653" roughness={1} />
      </mesh>

      {/* Static entities */}
      {(envState.entities || []).map(ent => {
        switch (ent.type) {
          case 'factory': return <Factory key={ent.id} entity={ent} />
          case 'building': return <Building key={ent.id} entity={ent} />
          case 'lake': return <Lake key={ent.id} entity={ent} />
          case 'forest': return <Forest key={ent.id} entity={ent} />
          default: return null
        }
      })}

      {/* CA Fire cells */}
      {(envState.ca_cells || []).map(cell => (
        <CaCell key={`${cell.i}_${cell.j}`} cell={cell} />
      ))}

      {/* Explored fog-of-war circles */}
      <ExploredCircles exploredCells={exploredCells} gridOffset={0} />

      {/* Home Base ring */}
      <mesh position={[ox, 0.05, oy]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[3, 4.5, 48]} />
        <meshBasicMaterial color="#ff4500" transparent opacity={0.6} />
      </mesh>

      {/* Left-click command plane — only mounted when a drone is selected */}
      <CommandPlane selectedDroneId={selectedDroneId} onMapCommand={onMapCommand} gridOffset={ox} />
    </group>
  )
}

// ─────────────────────────────────────────────
// Collapsible Map Legend
// ─────────────────────────────────────────────
function MapLegend() {
  const [open, setOpen] = useState(true)

  const items = [
    { color: '#1e5235', label: 'Forest', shape: '▲' },
    { color: '#0a2c59', label: 'Lake', shape: '■' },
    { color: '#2e3b4e', label: 'Building', shape: '■' },
    { color: '#4a4a4a', label: 'Factory', shape: '■' },
    { color: '#ffcc00', label: 'Early Fire', shape: '●' },
    { color: '#ff3300', label: 'Full Fire', shape: '●' },
    { color: '#8b1a1a', label: 'Extinguishing', shape: '●' },
    { color: '#333333', label: 'Ash', shape: '■' },
    { color: '#00ffcc', label: 'Drone / Sensor', shape: '○' },
    { color: '#a855f7', label: 'DSP Target', shape: '◆' },
    { color: '#00ffcc', label: 'Explored Area', shape: '○' },
    { color: '#ff4500', label: 'Home Base', shape: '○' },
  ]

  return (
    <div className="absolute bottom-4 left-4 z-10 select-none">
      <div className={`bg-card/90 backdrop-blur border border-white/10 rounded-xl shadow-2xl
        transition-all duration-300 overflow-hidden
        ${open ? 'w-48 pb-2' : 'w-10 h-10'}`}>
        <button
          onClick={() => setOpen(o => !o)}
          className="flex items-center justify-between w-full px-3 py-2 hover:bg-white/5 rounded-t-xl"
        >
          {open && <span className="text-xs font-semibold text-slate-300 tracking-wider uppercase">Legend</span>}
          <span className={`text-slate-400 transition-transform duration-300 ${open ? '' : 'rotate-180'}`}>
            {open ? '▼' : '▶'}
          </span>
        </button>
        {open && (
          <div className="px-3 space-y-1">
            {items.map(item => (
              <div key={item.label} className="flex items-center gap-2">
                <span style={{ color: item.color }} className="text-sm w-4 text-center shrink-0">
                  {item.shape}
                </span>
                <span className="text-xs text-slate-400">{item.label}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────
// Main export
// ─────────────────────────────────────────────
export default function MapGrid({
  active, envState, drones = {}, identifiedFires = [],
  selectedDroneId, onDroneSelect, onMapCommand, missionResults
}) {
  const gridOffset = envState?.grid?.width ? envState.grid.width / (2 * SCALE) : 100

  // Fog of war: track explored cell keys "x|z" in Three.js space
  const [exploredCells, setExploredCells] = useState(new Set())

  useEffect(() => {
    // Clear explored cells on reset
    if (!envState) {
      setExploredCells(new Set());
    }
  }, [envState]);

  useEffect(() => {
    if (!active) return
    const radius = 6000 / SCALE
    const step = radius * 1.2
    setExploredCells(prev => {
      const next = new Set(prev)
      Object.values(drones).forEach(d => {
        const tx = (d.x / SCALE)
        const tz = (d.y / SCALE)
        // snap to grid for deduplication
        const gx = Math.round(tx / step) * step
        const gz = Math.round(tz / step) * step
        next.add(`${gx.toFixed(1)}|${gz.toFixed(1)}`)
      })
      return next
    })
  }, [drones, active])

  return (
    <div className="w-full h-full relative">
      <Canvas
        shadows
        camera={{ position: [0, 100, 120], fov: 45 }}
        onCreated={({ gl }) => {
          gl.shadowMap.enabled = true
          gl.shadowMap.type = THREE.PCFSoftShadowMap
        }}
      >
        <color attach="background" args={['#9b7653']} />
        <ambientLight intensity={0.5} />
        {/* <directionalLight
          position={[150, 250, 100]} intensity={1.5} castShadow
          shadow-mapSize={[2048, 2048]}
          shadow-camera-far={400}
          shadow-camera-left={-250} shadow-camera-right={250}
          shadow-camera-top={250} shadow-camera-bottom={-250}
        /> */}
        <Environment preset="night" />

        <World
          envState={envState}
          identifiedFires={identifiedFires}
          exploredCells={exploredCells}
          selectedDroneId={selectedDroneId}
          onMapCommand={onMapCommand}
        />

        {/* Drones offset to match world centering */}
        <group position={[-gridOffset, 0, -gridOffset]}>
          {active && Object.values(drones).map(drone => (
            <Drone
              key={drone.drone_id}
              pose={drone}
              isSelected={drone.drone_id === selectedDroneId}
              onSelect={onDroneSelect}
            />
          ))}

          {/* Live Progress Paths */}
          {active && Object.values(drones).map((drone, idx) => (
            drone.path && (
              <DronePath
                key={`live_path_${drone.drone_id}`}
                path={drone.path}
                color={new THREE.Color().setHSL(idx / 10, 0.7, 0.5).getStyle()}
              />
            )
          ))}

          {/* Mission Result Paths */}
          {!active && missionResults?.drone_paths &&
            Object.entries(missionResults.drone_paths).map(([id, path], idx) => (
              <DronePath
                key={`path_${id}`}
                path={path}
                color={new THREE.Color().setHSL(idx / 10, 0.7, 0.5).getStyle()}
              />
            ))
          }
        </group>

        {/* Disable left-mouse orbit when a drone is selected so left-click
            reaches the CommandPlane instead of rotating the camera. */}
        <OrbitControls
          enableDamping
          dampingFactor={0.05}
          maxPolarAngle={Math.PI / 2.05}
          minDistance={5}
          maxDistance={350}
          mouseButtons={selectedDroneId
            ? { MIDDLE: 2, RIGHT: 1 }   // left-button removed
            : { LEFT: 0, MIDDLE: 2, RIGHT: 1 }}
        />
      </Canvas>

      <MapLegend />

      {!active && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none bg-dark/40 backdrop-blur-[2px]">
          <div className="px-6 py-3 rounded-full border border-white/10 bg-black/60 text-slate-400 font-mono text-sm tracking-widest shadow-2xl">
            AWAITING DEPLOYMENT
          </div>
        </div>
      )}

      {/* Left-click hint when drone selected */}
      {selectedDroneId && active && (
        <div className="absolute bottom-4 right-4 px-3 py-2 rounded-lg bg-black/60 border border-purple-500/30 text-purple-300 text-xs font-mono pointer-events-none animate-pulse">
          🖱 Click map to send drone there
        </div>
      )}
    </div>
  )
}
