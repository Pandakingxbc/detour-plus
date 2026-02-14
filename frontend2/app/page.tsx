import { DashboardHeader } from "@/components/dashboard-header"
import { GlobeView } from "@/components/globe-view"

export default function HomePage() {
  return (
    <main className="relative h-screen w-screen overflow-hidden bg-background text-foreground">
      <GlobeView />
      <div className="pointer-events-none absolute inset-x-0 top-0 z-20 p-6">
        <div className="pointer-events-auto mx-auto w-full max-w-[1600px]">
          <DashboardHeader />
        </div>
      </div>
    </main>
  )
}
