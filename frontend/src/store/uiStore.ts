import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type {
  ThemeState,
  PermissionModeState,
  ThinkingModeState,
  UIState,
  UIActions,
} from '@/types';
import { MOBILE_BREAKPOINT } from '@/config/constants';

type UIStoreState = ThemeState &
  PermissionModeState &
  ThinkingModeState &
  Pick<UIState, 'sidebarOpen' | 'currentView'> &
  Pick<UIActions, 'setSidebarOpen' | 'setCurrentView'>;

const getInitialSidebarState = (): boolean => {
  if (typeof window === 'undefined') return false;
  return window.innerWidth >= MOBILE_BREAKPOINT;
};

export const useUIStore = create<UIStoreState>()(
  persist(
    (set) => ({
      theme: 'dark',
      toggleTheme: () =>
        set((state) => ({
          theme: state.theme === 'dark' ? 'light' : 'dark',
        })),
      permissionMode: 'auto',
      setPermissionMode: (mode) => set({ permissionMode: mode }),
      thinkingMode: null,
      setThinkingMode: (mode) => set({ thinkingMode: mode }),
      sidebarOpen: getInitialSidebarState(),
      currentView: 'agent',
      setSidebarOpen: (isOpen) => set({ sidebarOpen: isOpen }),
      setCurrentView: (view) => set({ currentView: view }),
    }),
    {
      name: 'ui-storage',
      partialize: (state) => ({
        theme: state.theme,
        permissionMode: state.permissionMode,
        thinkingMode: state.thinkingMode,
        currentView: state.currentView,
      }),
      merge: (persisted, current) => {
        const persistedState = persisted as Partial<UIStoreState> | undefined;
        return {
          ...current,
          ...persistedState,
          sidebarOpen: getInitialSidebarState(),
        };
      },
    },
  ),
);
