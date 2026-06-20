import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import SettingsView from '../views/SettingsView.vue'
import ProjectView from '../views/ProjectView.vue'
import SeriesView from '../views/SeriesView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/settings', name: 'settings', component: SettingsView },
    { path: '/project/:id', name: 'project', component: ProjectView },
    { path: '/series/:id', name: 'series', component: SeriesView }
  ]
})

export default router
