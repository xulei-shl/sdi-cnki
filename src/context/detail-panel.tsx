import { createContext, useContext, type ReactNode } from 'react'

interface DetailPanelState {
  open: boolean
  content: ReactNode | null
  title: string
  openPanel: (title: string, content: ReactNode) => void
  closePanel: () => void
}

const DetailPanelContext = createContext<DetailPanelState | undefined>(undefined)

export function DetailPanelProvider({ children, value }: { children: ReactNode; value: DetailPanelState }) {
  return (
    <DetailPanelContext.Provider value={value}>
      {children}
    </DetailPanelContext.Provider>
  )
}

export function useDetailPanel() {
  const context = useContext(DetailPanelContext)
  if (!context) throw new Error('useDetailPanel must be used within DetailPanelProvider')
  return context
}

export type { DetailPanelState }
