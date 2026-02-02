import React, { useState } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { Dashboard } from './components/Dashboard';
import { MeshTopology } from './components/MeshTopology';
import { IntentRouter } from './components/IntentRouter';
import { AgentInspector } from './components/AgentInspector';
import { GossipFeed } from './components/GossipFeed';
import { JoinPanel } from './components/JoinPanel';
import { IntegrationPanel } from './components/IntegrationPanel';
import { 
  LayoutDashboard, 
  Network, 
  Zap, 
  Activity, 
  Radio, 
  Link2,
  Puzzle,
  Menu,
  X
} from 'lucide-react';
import './App.css';

const pages = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, component: Dashboard },
  { id: 'topology', label: 'Mesh Topology', icon: Network, component: MeshTopology },
  { id: 'router', label: 'Intent Router', icon: Zap, component: IntentRouter },
  { id: 'agents', label: 'Agent Inspector', icon: Activity, component: AgentInspector },
  { id: 'integrations', label: 'Integrations', icon: Puzzle, component: IntegrationPanel },
  { id: 'gossip', label: 'Gossip Feed', icon: Radio, component: GossipFeed },
  { id: 'join', label: 'Join Mesh', icon: Link2, component: JoinPanel },
];

function App() {
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [menuOpen, setMenuOpen] = useState(false);
  const { isConnected, lastMessage } = useWebSocket('/ws');

  const CurrentComponent = pages.find(p => p.id === currentPage)?.component || Dashboard;

  return (
    <div className="app">
      <nav className="sidebar">
        <div className="sidebar-header">
          <div className="logo">
            <div className="logo-icon">A</div>
            <div className="logo-text">
              <div className="logo-title">Atmosphere</div>
              <div className="logo-subtitle">Mesh Network</div>
            </div>
          </div>
          
          <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
            <div className="status-dot"></div>
            <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
        </div>

        <div className="nav-items">
          {pages.map(page => {
            const Icon = page.icon;
            return (
              <button
                key={page.id}
                onClick={() => {
                  setCurrentPage(page.id);
                  setMenuOpen(false);
                }}
                className={`nav-item ${currentPage === page.id ? 'active' : ''}`}
              >
                <Icon size={20} />
                <span>{page.label}</span>
              </button>
            );
          })}
        </div>

        <div className="sidebar-footer">
          <div className="footer-text">
            Built with Atmosphere
          </div>
        </div>
      </nav>

      <button 
        className="mobile-menu-button"
        onClick={() => setMenuOpen(!menuOpen)}
      >
        {menuOpen ? <X size={24} /> : <Menu size={24} />}
      </button>

      {menuOpen && (
        <div className="mobile-overlay" onClick={() => setMenuOpen(false)}>
          <div className="mobile-menu" onClick={e => e.stopPropagation()}>
            <div className="mobile-header">
              <div className="logo-text">
                <div className="logo-title">Atmosphere</div>
                <div className="logo-subtitle">Mesh Network</div>
              </div>
            </div>
            
            <div className="mobile-nav-items">
              {pages.map(page => {
                const Icon = page.icon;
                return (
                  <button
                    key={page.id}
                    onClick={() => {
                      setCurrentPage(page.id);
                      setMenuOpen(false);
                    }}
                    className={`nav-item ${currentPage === page.id ? 'active' : ''}`}
                  >
                    <Icon size={20} />
                    <span>{page.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <main className="main-content">
        <CurrentComponent wsData={lastMessage} />
      </main>
    </div>
  );
}

export default App;
