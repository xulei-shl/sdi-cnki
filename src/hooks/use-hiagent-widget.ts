import { useEffect, useRef } from 'react'

export function useHiagentWidget(appKey: string) {
  const instanceRef = useRef<any>(null)

  useEffect(() => {
    const script = document.createElement('script')
    script.src = 'https://hiagent.library.sh.cn/resources/product/llm/public/sdk/embedLite.js'
    script.onload = () => {
      try {
        instanceRef.current = new (window as any).HiagentWebSDK.WebLiteClient({
          appKey,
          baseUrl: 'https://hiagent.library.sh.cn',
        })
      } catch (err) {
        console.error('Hiagent widget init failed', err)
      }
    }
    script.onerror = () => {
      console.error('Hiagent SDK script load failed')
    }
    document.body.appendChild(script)

    return () => {
      const inst = instanceRef.current
      if (inst) {
        try {
          ;(inst as any).destroy?.()
          ;(inst as any).dispose?.()
          ;(inst as any).cleanup?.()
          ;(inst as any).unmount?.()
        } catch { /* ignore */ }
      }
      document.querySelectorAll('[class*="hiagent"],[class*="Hiagent"],[id*="hiagent"],[id*="Hiagent"]')
        .forEach(el => el.remove())
      if (script.parentNode) script.parentNode.removeChild(script)
    }
  }, [appKey])
}
