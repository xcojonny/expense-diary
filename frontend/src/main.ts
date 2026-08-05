import { createApp } from 'vue'

import App from './App.vue'
import { router } from './router'
import { initTheme } from './lib/theme'
import './styles/base.css'

// Vor dem ersten Rendern, sonst blitzt kurz das falsche Theme auf.
initTheme()

createApp(App).use(router).mount('#app')
