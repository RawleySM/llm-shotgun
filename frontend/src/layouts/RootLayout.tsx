import { Link, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { AppProvider } from '../context/AppContext'
import { Notification } from '../components/ui/Notification'
import { ThemeToggle } from '../components/ui/ThemeToggle'
import { useAuth } from '../context/AuthContext'
import { Button } from '../components/ui/Button'

const publicNavLinks = [
  { to: '/', label: 'Home' },
  { to: '/about', label: 'About' },
] as const

const privateNavLinks = [{ to: '/dashboard', label: 'Dashboard' }] as const

function Navigation() {
  const navigate = useNavigate()
  const location = useLocation()
  const { isAuthenticated, logout } = useAuth()
  const linkBase =
    'text-card-foreground hover:text-primary hover:bg-accent/20 px-3 py-2 rounded-md text-sm font-medium transition-colors'
  const activeLink = 'text-primary font-semibold underline underline-offset-4'

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <nav className="bg-card text-card-foreground shadow-sm transition-colors">
      <div className="container mx-auto px-6">
        <div className="flex justify-between h-16 items-center">
          <div className="flex space-x-8">
            {publicNavLinks.map(({ to, label }) => (
              <Link
                key={to}
                to={to}
                className={location.pathname === to ? `${linkBase} ${activeLink}` : linkBase}
              >
                {label}
              </Link>
            ))}
            {isAuthenticated &&
              privateNavLinks.map(({ to, label }) => (
                <Link
                  key={to}
                  to={to}
                  className={location.pathname === to ? `${linkBase} ${activeLink}` : linkBase}
                >
                  {label}
                </Link>
              ))}
          </div>
          <div className="flex items-center space-x-4">
            <ThemeToggle />
            {isAuthenticated ? (
              <Button
                variant="ghost"
                onClick={handleLogout}
                className="text-card-foreground hover:text-primary hover:bg-accent/20"
              >
                Logout
              </Button>
            ) : (
              <Link
                to="/login"
                className={location.pathname === '/login' ? `${linkBase} ${activeLink}` : linkBase}
              >
                Login
              </Link>
            )}
          </div>
        </div>
      </div>
    </nav>
  )
}

export default function RootLayout() {
  const currentYear = new Date().getFullYear()

  return (
    <AppProvider>
      <div className="min-h-screen flex flex-col bg-background text-foreground transition-colors">
        <Navigation />
        <main className="flex-1 container mx-auto px-6 py-8">
          <Outlet />
        </main>
        <footer className="bg-card text-card-foreground shadow-sm transition-colors mt-auto">
          <div className="container mx-auto px-6 py-4">
            <p className="text-center text-muted-foreground">
              {currentYear} FastAPI React Starter. All rights reserved.
            </p>
          </div>
        </footer>
        <Notification />
      </div>
    </AppProvider>
  )
}
