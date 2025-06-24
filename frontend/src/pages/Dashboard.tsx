import { Suspense } from 'react'
import { ChartColumnIncreasing, Clock1, Zap } from 'lucide-react'
import { useAppDispatch } from '../context/AppContext'
import { showNotification } from '../context/AppContext'

export default function Dashboard() {
  const dispatch = useAppDispatch()

  const handleCardClick = (title: string) => {
    showNotification(dispatch, `Clicked ${title} card`, 'info')
  }

  return (
    <div className="space-y-8">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4 text-foreground">Dashboard</h1>
        <p className="text-lg text-muted-foreground">
          Monitor your application metrics and performance
        </p>
      </div>

      <Suspense
        fallback={
          <div className="text-center py-8 text-muted-foreground">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4" />
            Loading dashboard data...
          </div>
        }
      >
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <DashboardCard
            title="Statistics"
            description="View key metrics and analytics"
            icon={<ChartColumnIncreasing />}
            onClick={handleCardClick}
          />
          <DashboardCard
            title="Recent Activity"
            description="Track the latest updates and changes"
            icon={<Clock1 />}
            onClick={handleCardClick}
          />
          <DashboardCard
            title="Performance"
            description="Monitor system performance metrics"
            icon={<Zap />}
            onClick={handleCardClick}
          />
        </div>
      </Suspense>
    </div>
  )
}

function DashboardCard({
  title,
  description,
  icon,
  onClick,
}: {
  title: string
  description: string
  icon: React.ReactNode
  onClick: (title: string) => void
}) {
  return (
    <div
      className="p-6 rounded-lg border border-border
        bg-card text-card-foreground shadow-sm hover:shadow-md transition-all
        cursor-pointer group"
      onClick={() => onClick(title)}
    >
      <div className="flex items-start space-x-4">
        <div
          className="flex-shrink-0 p-2 rounded-lg bg-accent text-accent-foreground
          group-hover:bg-accent/80 dark:group-hover:bg-accent/80 transition-colors"
        >
          {icon}
        </div>
        <div>
          <h2
            className="text-xl font-semibold mb-2 text-card-foreground group-hover:text-primary
            transition-colors"
          >
            {title}
          </h2>
          <p className="text-muted-foreground">{description}</p>
        </div>
      </div>
    </div>
  )
}
