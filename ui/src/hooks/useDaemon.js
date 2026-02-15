import { useEffect, useState, useCallback } from 'react';

/**
 * Hook to interact with atmosphere-core daemon
 * HTTP API on port 11462, provides status, peer info, capabilities
 */
export const useDaemon = (baseUrl = 'http://localhost:11462') => {
  const [isConnected, setIsConnected] = useState(false);
  const [daemonStatus, setDaemonStatus] = useState(null);
  const [peers, setPeers] = useState([]);
  const [capabilities, setCapabilities] = useState([]);
  const [bigLlamaStatus, setBigLlamaStatus] = useState(null);

  // Poll daemon status
  useEffect(() => {
    const checkStatus = async () => {
      try {
        // Try to hit the health endpoint (we'll need to add this to the daemon)
        // For now, try a simple fetch to see if the server is up
        const response = await fetch(`${baseUrl}/health`, { 
          method: 'GET',
          headers: { 'Accept': 'application/json' }
        });
        
        if (response.ok) {
          const data = await response.json();
          setDaemonStatus(data);
          setIsConnected(true);
        } else {
          setIsConnected(false);
        }
      } catch (error) {
        setIsConnected(false);
      }
    };

    checkStatus();
    const interval = setInterval(checkStatus, 5000); // Poll every 5s
    
    return () => clearInterval(interval);
  }, [baseUrl]);

  // Fetch peer info (we'll need to add API endpoints for this)
  const fetchPeers = useCallback(async () => {
    try {
      const response = await fetch(`${baseUrl}/api/peers`);
      if (response.ok) {
        const data = await response.json();
        setPeers(data.peers || []);
      }
    } catch (error) {
      console.error('Failed to fetch peers:', error);
    }
  }, [baseUrl]);

  // Fetch capabilities from CRDT
  const fetchCapabilities = useCallback(async () => {
    try {
      const response = await fetch(`${baseUrl}/api/capabilities`);
      if (response.ok) {
        const data = await response.json();
        setCapabilities(data.capabilities || []);
      }
    } catch (error) {
      console.error('Failed to fetch capabilities:', error);
    }
  }, [baseUrl]);

  // Fetch BigLlama status
  const fetchBigLlamaStatus = useCallback(async () => {
    try {
      const response = await fetch(`${baseUrl}/api/bigllama/status`);
      if (response.ok) {
        const data = await response.json();
        setBigLlamaStatus(data);
      }
    } catch (error) {
      console.error('Failed to fetch BigLlama status:', error);
    }
  }, [baseUrl]);

  // Periodic refresh
  useEffect(() => {
    if (isConnected) {
      fetchPeers();
      fetchCapabilities();
      fetchBigLlamaStatus();

      const interval = setInterval(() => {
        fetchPeers();
        fetchCapabilities();
        fetchBigLlamaStatus();
      }, 10000); // Refresh every 10s

      return () => clearInterval(interval);
    }
  }, [isConnected, fetchPeers, fetchCapabilities, fetchBigLlamaStatus]);

  return {
    isConnected,
    daemonStatus,
    peers,
    capabilities,
    bigLlamaStatus,
    refresh: {
      peers: fetchPeers,
      capabilities: fetchCapabilities,
      bigLlama: fetchBigLlamaStatus,
    }
  };
};
