import React from 'react';
import { Users, Check } from 'lucide-react';
import { useStore, USERS } from '../../context/StoreContext';
import Modal from '../shared/Modal';

export default function UserSwitchModal() {
  const { currentUser, switchUser, isUserModalOpen, setIsUserModalOpen } = useStore();

  return (
    <Modal
      isOpen={isUserModalOpen}
      onClose={() => setIsUserModalOpen(false)}
      title="Switch Active Customer Profile"
      icon={Users}
      maxWidth="440px"
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {USERS.map((user) => {
          const isActive = user.id === currentUser.id;
          return (
            <div
              key={user.id}
              onClick={() => switchUser(user)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.85rem 1rem',
                borderRadius: '10px',
                background: isActive ? 'rgba(6, 182, 212, 0.15)' : 'rgba(255, 255, 255, 0.04)',
                border: `1px solid ${isActive ? 'var(--cyan-400)' : 'rgba(255, 255, 255, 0.08)'}`,
                cursor: 'pointer',
                transition: 'all 0.2s ease'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                <div style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '50%',
                  background: isActive ? 'linear-gradient(135deg, #06b6d4, #3b82f6)' : 'rgba(255, 255, 255, 0.1)',
                  color: '#fff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  fontSize: '0.85rem'
                }}>
                  {user.initials}
                </div>
                <div>
                  <h5 style={{ color: '#fff', fontSize: '0.9rem', fontWeight: 700 }}>
                    {user.name} {isActive && <span style={{ color: '#06b6d4', fontSize: '0.75rem' }}>(Active)</span>}
                  </h5>
                  <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>{user.email}</span>
                </div>
              </div>

              {isActive && <Check size={18} style={{ color: '#06b6d4' }} />}
            </div>
          );
        })}
      </div>
    </Modal>
  );
}
