import { useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Grid, Environment } from '@react-three/drei'

// Mock drone moving in a circle
function Drone({ position, baseRadius, speed, color }) {
  const meshRef = useRef()

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    meshRef.current.position.x = Math.cos(t * speed) * baseRadius
    meshRef.current.position.z = Math.sin(t * speed) * baseRadius
    // Hover effect
    meshRef.current.position.y = 2 + Math.sin(t * 5 + baseRadius) * 0.5
  })

  return (
    <mesh ref={meshRef} position={position} castShadow>
      <sphereGeometry args={[0.3, 16, 16]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={2} />
    </mesh>
  )
}

export default function MapGrid({ active }) {
  return (
    <div className="w-full h-full relative">
      <Canvas shadows camera={{ position: [0, 15, 20], fov: 45 }}>
        <color attach="background" args={['#0B0F19']} />

        {/* Cinematic Lighting */}
        <ambientLight intensity={0.2} />
        <directionalLight position={[10, 20, 5]} intensity={1.5} castShadow />
        <pointLight position={[0, 5, 0]} intensity={2} color="#FF4500" distance={20} />

        {/* Environment Map for reflections */}
        <Environment preset="night" />

        {/* High-tech Grid */}
        <Grid
          renderOrder={-1}
          position={[0, 0, 0]}
          infiniteGrid
          cellSize={1}
          cellThickness={0.5}
          sectionSize={5}
          sectionThickness={1}
          sectionColor="#FF4500"
          fadeDistance={50}
          cellColor="#1E2A44"
        />

        {/* Center Target Indicator (Spawn point) */}
        <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[1.8, 2, 32]} />
          <meshBasicMaterial color="#FF4500" transparent opacity={0.5} />
        </mesh>

        {/* Drones */}
        {active && (
          <>
            <Drone position={[5, 2, 0]} baseRadius={8} speed={0.5} color="#00ffcc" />
            <Drone position={[-3, 2.5, 3]} baseRadius={5} speed={-0.7} color="#00ffcc" />
            <Drone position={[0, 1.5, -6]} baseRadius={12} speed={0.3} color="#00ffcc" />
            <Drone position={[2, 2.2, 2]} baseRadius={6} speed={0.8} color="#00ffcc" />
          </>
        )}

        {/* The Fire (Mocked target point) */}
        <mesh position={[0, 0.5, 0]}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial color="#FF4500" emissive="#FF4500" emissiveIntensity={active ? 2 : 0} />
        </mesh>

        <OrbitControls
          enableDamping
          dampingFactor={0.05}
          maxPolarAngle={Math.PI / 2.1} // Prevent looking from below
          minDistance={5}
          maxDistance={40}
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
