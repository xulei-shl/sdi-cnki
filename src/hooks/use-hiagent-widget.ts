import { useEffect } from 'react'

const SDK_CLASSES = [
  'hiagent-bubble-container',
  'hiagent-bubble',
  'hiagent-bubble-image',
  'hiagent-bubble-tooltip',
  'hiagent-bubble-tooltip-text',
  'hiagent-bubble-tooltip-arrow',
  'hiagent-conversation',
  'hiagent-conversation-iframe',
]

export function useHiagentWidget(appKey: string, baseUrl = 'https://hiagent.library.sh.cn') {
  useEffect(() => {
    function init() {
      try {
        new (window as any).HiagentWebSDK.WebLiteClient({ appKey, baseUrl })
      } catch (err) {
        console.error('Hiagent init failed:', err)
      }
    }

    // P3-1: Defer SDK init so it doesn't compete with first-paint / data fetching
    const timer = setTimeout(() => {
      if ((window as any).HiagentWebSDK?.WebLiteClient) {
        init()
      } else {
        // SDK not loaded yet — wait for it
        const onSdkReady = () => {
          init()
          window.removeEventListener('hiagent:ready', onSdkReady)
        }
        window.addEventListener('hiagent:ready', onSdkReady)
      }
    }, 2000)

    return () => {
      clearTimeout(timer)
      SDK_CLASSES.forEach(cls => {
        document.querySelectorAll(`.${cls}`).forEach(el => el.remove())
      })
      document.querySelectorAll('style').forEach(el => {
        if (el.textContent?.includes('hiagent-bubble')) el.remove()
      })
    }
  }, [appKey, baseUrl])
}
