import { Dna, Github, Key, Layers, LogOut, Menu, Search, User, X } from 'lucide-react';
import { useState } from 'react';
import { Link, Outlet, useNavigate } from 'react-router-dom';
import { AuthProvider, useAuthState } from '../hooks/useAuth';
import { Button } from './ui/button';
import { Input } from './ui/input';

const NAV_LINKS = [
  { to: '/browse', label: '基因', icon: Dna },
  { to: '/genomes', label: '基因组', icon: Layers },
  { to: '/templates', label: 'AI 员工模板', icon: User },
];

export default function Layout() {
  const [query, setQuery] = useState('');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const navigate = useNavigate();
  const authState = useAuthState();
  const { user, isLoading, login, logout } = authState;

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim()) {
      navigate(`/browse?q=${encodeURIComponent(query.trim())}`);
      setMobileMenuOpen(false);
    }
  }

  async function handleLogout() {
    await logout();
    setUserMenuOpen(false);
  }

  return (
    <div className="min-h-screen flex flex-col bg-surface-alt">
      <header className="bg-surface border-b border-border sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2 shrink-0">
            <span className="text-2xl">&#x1f9ec;</span>
            <span className="text-xl font-bold text-gray-900">GeneHub</span>
          </Link>

          <form onSubmit={handleSearch} className="flex-1 max-w-lg hidden md:block">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索基因..."
                className="pl-9 bg-surface-alt"
              />
            </div>
          </form>

          <nav className="hidden md:flex items-center gap-1 text-sm">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-muted hover:text-gray-900 hover:bg-gray-100 transition"
              >
                <link.icon className="w-4 h-4" />
                {link.label}
              </Link>
            ))}
            <a
              href="https://github.com/NoDeskAI/genehub"
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-muted hover:text-gray-900 hover:bg-gray-100 transition"
            >
              <Github className="w-4 h-4" />
              GitHub
            </a>
          </nav>

          <div className="hidden md:block">
            {isLoading ? null : user ? (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setUserMenuOpen((v) => !v)}
                  className="flex items-center gap-2 rounded-full hover:ring-2 hover:ring-gray-200 transition"
                >
                  <img
                    src={user.github_avatar_url}
                    alt={user.github_login}
                    className="w-8 h-8 rounded-full"
                  />
                </button>
                {userMenuOpen && (
                  <>
                    <button
                      type="button"
                      className="fixed inset-0 z-40 cursor-default"
                      onClick={() => setUserMenuOpen(false)}
                      aria-label="Close menu"
                    />
                    <div className="absolute right-0 mt-2 w-48 bg-surface border border-border rounded-lg shadow-lg z-50 py-1">
                      <div className="px-3 py-2 border-b border-border">
                        <p className="text-sm font-medium">
                          {user.github_name || user.github_login}
                        </p>
                        <p className="text-xs text-muted">@{user.github_login}</p>
                      </div>
                      <Link
                        to="/settings/keys"
                        onClick={() => setUserMenuOpen(false)}
                        className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 transition"
                      >
                        <Key className="w-4 h-4" />
                        API Keys
                      </Link>
                      <button
                        type="button"
                        onClick={handleLogout}
                        className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 hover:bg-gray-50 transition"
                      >
                        <LogOut className="w-4 h-4" />
                        退出
                      </button>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <Button variant="outline" size="sm" onClick={login}>
                <Github className="w-4 h-4 mr-1.5" />
                Login
              </Button>
            )}
          </div>

          <button
            type="button"
            className="md:hidden p-2 text-muted hover:text-gray-900"
            onClick={() => setMobileMenuOpen((v) => !v)}
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

        {mobileMenuOpen && (
          <div className="md:hidden border-t border-border px-4 py-4 space-y-3 bg-surface">
            <form onSubmit={handleSearch}>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="搜索基因..."
                  className="pl-9"
                />
              </div>
            </form>
            {NAV_LINKS.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                onClick={() => setMobileMenuOpen(false)}
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-muted hover:text-gray-900 hover:bg-gray-100 transition"
              >
                <link.icon className="w-4 h-4" />
                {link.label}
              </Link>
            ))}
            {!isLoading && !user && (
              <button
                type="button"
                onClick={login}
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-muted hover:text-gray-900 hover:bg-gray-100 transition w-full"
              >
                <Github className="w-4 h-4" />
                Login with GitHub
              </button>
            )}
          </div>
        )}
      </header>

      <main className="flex-1">
        <AuthProvider value={authState}>
          <Outlet />
        </AuthProvider>
      </main>

      <footer className="bg-surface border-t border-border py-8 text-sm text-muted">
        <div className="max-w-6xl mx-auto px-4 flex flex-col md:flex-row justify-between items-center gap-4">
          <div>GeneHub -- NoDeskAI</div>
          <div className="flex gap-6">
            <a
              href="https://github.com/NoDeskAI/genehub"
              target="_blank"
              rel="noreferrer"
              className="hover:text-gray-900 transition"
            >
              GitHub
            </a>
            <a
              href="https://github.com/NoDeskAI/genehub/issues"
              target="_blank"
              rel="noreferrer"
              className="hover:text-gray-900 transition"
            >
              反馈
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
