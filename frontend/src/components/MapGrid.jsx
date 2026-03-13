import { useRef, useEffect } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Environment } from '@react-three/drei'
import * as THREE from 'three'

// Constants for scaling the 651km world to screen space
const SCALE = 3000.0;

function Drone({ id, pose, color }) {
  const meshRef = useRef()
  const targetPos = useRef(new THREE.Vector3(pose.x / SCALE, pose.alt / 100, pose.y / SCALE))

  useEffect(() => {
    // Update target position when pose changes
    targetPos.current.set(pose.x / SCALE, pose.alt / 100, pose.y / SCALE)
  }, [pose])

  useFrame((state, delta) => {
    // Smoothly interpolate current position towards target position
    if (meshRef.current) {
      meshRef.current.position.lerp(targetPos.current, 0.1)
    }
  })

  return (
    <group ref={meshRef}>
      <mesh castShadow>
        <sphereGeometry args={[0.8, 16, 16]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={2} />
      </mesh>
      {/* 6km Pheromone/Sensor Range Indicator */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.2, 0]}>
        <ringGeometry args={[6000/SCALE - 0.2, 6000/SCALE, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.3} />
      </mesh>
    </group>
  )
}

function Wildfire({ fire, isIdentified }) {
    const fireRef = useRef()
    const color = isIdentified ? "#ff9500" : "#ff0000" // Orange if identified, Red if unknown

    useFrame(({ clock }) => {
        const t = clock.getElapsedTime()
        if (fireRef.current) {
            fireRef.current.scale.setScalar(1 + Math.sin(t * 8) * 0.1)
        }
    })

    return (
       <group position={[fire.x / SCALE, 1, fire.y / SCALE]}>
           <mesh ref={fireRef} castShadow>
               <sphereGeometry args={[fire.size / SCALE, 16, 16]} />
               <meshStandardMaterial color={color} emissive={color} emissiveIntensity={2} />
           </mesh>
           <pointLight color={color} intensity={2} distance={30} />
       </group>
    )
}

function Factory({ entity }) {
  const smokeLightRef = useRef()

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    if (smokeLightRef.current) {
        smokeLightRef.current.intensity = 1.5 + Math.sin(t * 10) * 0.5
    }
  })

  return (
    <group position={[entity.x / SCALE, 0.5, entity.y / SCALE]}>
       <mesh castShadow receiveShadow position={[0, 0.5, 0]}>
         <boxGeometry args={[entity.size/SCALE, 2, entity.size/SCALE]} />
         <meshStandardMaterial color="#4A4A4A" roughness={0.9} />
       </mesh>
       <pointLight ref={smokeLightRef} position={[0, 3, 0]} color="#FF4500" distance={10} inline />
       <mesh position={[entity.size/(SCALE*2.5), 2.5, entity.size/(SCALE*2.5)]}>
         <cylinderGeometry args={[0.5, 0.5, 2, 8]} />
         <meshStandardMaterial color="#2d2d2d" />
       </mesh>
    </group>
  )
}

function Building({ entity }) {
  const scaledH = entity.height / 100 // Visual height scale
  return (
    <mesh position={[entity.x / SCALE, scaledH/2, entity.y / SCALE]} castShadow receiveShadow>
       <boxGeometry args={[entity.size/SCALE, scaledH, entity.size/SCALE]} />
       <meshStandardMaterial color="#2E3B4E" roughness={0.7} border />
    </mesh>
  )
}

function Lake({ entity }) {
  return (
    <mesh position={[entity.x / SCALE, 0.05, entity.y / SCALE]} rotation={[-Math.PI/2, 0, 0]} receiveShadow>
       <planeGeometry args={[entity.size/SCALE, entity.size/SCALE]} />
       <meshStandardMaterial color="#0A2C59" transparent opacity={0.6} roughness={0.1} />
    </mesh>
  )
}

function Forest({ entity }) {
  return (
    <mesh position={[entity.x / SCALE, 0.5, entity.y / SCALE]} castShadow>
       <coneGeometry args={[entity.size/(SCALE*2), 1.5, 8]} />
       <meshStandardMaterial color="#1E5235" roughness={0.8} />
    </mesh>
  )
}

function World({ envState, identifiedFires }) {
  if (!envState || !envState.entities) return null;

  const centerOffsetX = envState.grid.width / (2 * SCALE)
  const centerOffsetY = envState.grid.height / (2 * SCALE)

  return (
    <group position={[-centerOffsetX, 0, -centerOffsetY]}>
        {/* World Base Plane */}
        <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[envState.grid.width/SCALE, envState.grid.height/SCALE]} />
          <meshStandardMaterial color="#0b1720" roughness={1} />
        </mesh>

        {envState.entities.map(ent => {
             switch(ent.type) {
                 case 'factory': return <Factory key={ent.id} entity={ent} />
                 case 'building': return <Building key={ent.id} entity={ent} />
                 case 'lake': return <Lake key={ent.id} entity={ent} />
                 case 'forest': return <Forest key={ent.id} entity={ent} />
                 default: return null
             }
        })}

        {envState.fires && envState.fires.map(fire => (
             <Wildfire key={fire.id} fire={fire} isIdentified={identifiedFires.includes(fire.id)} />
        ))}

        {/* Center Target Indicator (Spawn point Home Base) */}
        <mesh position={[centerOffsetX, 0.05, centerOffsetY]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[3, 4, 32]} />
          <meshBasicMaterial color="#FF4500" transparent opacity={0.5} />
        </mesh>
    </group>
  )
}


export default function MapGrid({ active, envState, drones, identifiedFires = [] }) {
  const centerOffset = envState?.grid?.width ? (envState.grid.width / (2 * SCALE)) : 50;

  return (
    <div className="w-full h-full relative">
      <Canvas shadows camera={{ position: [0, 150, 150], fov: 45 }}>
        <color attach="background" args={['#05080f']} />

        <ambientLight intensity={0.2} />
        <directionalLight position={[200, 300, 100]} intensity={1.5} castShadow shadow-mapSize={[2048, 2048]} shadow-camera-far={400} shadow-camera-left={-200} shadow-camera-right={200} shadow-camera-top={200} shadow-camera-bottom={-200} />

        <Environment preset="night" />

        <World envState={envState} identifiedFires={identifiedFires} />

        {/* Drones */}
        <group position={[-centerOffset, 0, -centerOffset]}>
          {active && drones && Object.values(drones).map(drone => (
              <Drone key={drone.drone_id} id={drone.drone_id} pose={drone} color="#00ffcc" />
          ))}
        </group>

        <OrbitControls
          enableDamping
          dampingFactor={0.05}
          maxPolarAngle={Math.PI / 2.1}
          minDistance={10}
          maxDistance={400}
        />
      </Canvas>

      {!active && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none bg-dark/40 backdrop-blur-[2px]">
          <div className="px-6 py-3 rounded-full border border-white/10 bg-black/60 text-slate-400 font-mono text-sm tracking-widest shadow-2xl">
            AWAITING DEPLOYMENT
          </div>
        </div>
      )}
    </div>
  )
}
