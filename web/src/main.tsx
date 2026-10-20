import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// No StrictMode: react-three-fiber's canvas container is unmounted twice under React 19's
// double-invoked effects, which removes the WebGL canvas from the page.
createRoot(document.getElementById('root')!).render(<App />)
