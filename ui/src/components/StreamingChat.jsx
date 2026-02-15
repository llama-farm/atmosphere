import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader, AlertCircle, MessageSquare } from 'lucide-react';
import './StreamingChat.css';

export const StreamingChat = ({ daemonUrl = 'http://localhost:11462' }) => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const messagesEndRef = useRef(null);
  const abortControllerRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || isStreaming) return;

    const userMessage = {
      role: 'user',
      content: input.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsStreaming(true);
    setError(null);

    // Create assistant message placeholder
    const assistantMessage = {
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      streaming: true,
    };
    setMessages(prev => [...prev, assistantMessage]);

    try {
      abortControllerRef.current = new AbortController();

      const response = await fetch(`${daemonUrl}/v1/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          messages: [{ role: 'user', content: userMessage.content }],
          stream: true,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            
            if (data === '[DONE]') {
              setIsStreaming(false);
              setMessages(prev => prev.map((msg, idx) => 
                idx === prev.length - 1 ? { ...msg, streaming: false } : msg
              ));
              break;
            }

            try {
              const parsed = JSON.parse(data);
              
              if (parsed.error) {
                setError(parsed.error.message || 'Unknown error');
                setIsStreaming(false);
                break;
              }

              const content = parsed.choices?.[0]?.delta?.content || '';
              
              if (content) {
                setMessages(prev => {
                  const updated = [...prev];
                  const lastMsg = updated[updated.length - 1];
                  lastMsg.content += content;
                  return updated;
                });
              }
            } catch (e) {
              console.warn('Failed to parse SSE data:', data, e);
            }
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('Request aborted');
      } else {
        console.error('Streaming error:', err);
        setError(err.message);
      }
      setIsStreaming(false);
      
      // Remove failed assistant message
      setMessages(prev => prev.filter((_, idx) => idx !== prev.length - 1));
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const stopStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
    }
  };

  return (
    <div className="streaming-chat">
      <div className="chat-header">
        <MessageSquare size={20} />
        <h2>Streaming Chat</h2>
        <span className="chat-status">
          {isStreaming ? '● Streaming...' : '○ Ready'}
        </span>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <MessageSquare size={48} opacity={0.2} />
            <p>Send a message to start chatting with the mesh</p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={idx} className={`chat-message ${msg.role}`}>
            <div className="message-role">
              {msg.role === 'user' ? 'You' : 'Assistant'}
            </div>
            <div className="message-content">
              {msg.content || (msg.streaming ? '...' : '')}
              {msg.streaming && <span className="cursor">▊</span>}
            </div>
            <div className="message-timestamp">
              {new Date(msg.timestamp).toLocaleTimeString()}
            </div>
          </div>
        ))}

        {error && (
          <div className="chat-error">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Type a message... (Enter to send, Shift+Enter for new line)"
          disabled={isStreaming}
          rows={3}
        />
        <button
          onClick={isStreaming ? stopStreaming : sendMessage}
          disabled={!input.trim() && !isStreaming}
          className={isStreaming ? 'stop' : 'send'}
        >
          {isStreaming ? (
            <>
              <Loader className="spinning" size={18} />
              Stop
            </>
          ) : (
            <>
              <Send size={18} />
              Send
            </>
          )}
        </button>
      </div>
    </div>
  );
};
