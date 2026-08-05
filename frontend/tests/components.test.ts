/**
 * Komponententests für das Verhalten, das im Altstand fehlte: der Altstand
 * hatte vier Tests, alle für reine Utils, und keinen einzigen für eine
 * Komponente.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'

import ResourceBoundary from '@/components/ResourceBoundary.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import UiMoneyInput from '@/ui/UiMoneyInput.vue'
import ChartBars from '@/charts/ChartBars.vue'
import ChartDonut from '@/charts/ChartDonut.vue'

describe('ResourceBoundary', () => {
  it('zeigt beim Laden einen Skeleton statt des Inhalts', () => {
    const wrapper = mount(ResourceBoundary, {
      props: { loading: true },
      slots: { default: '<p>Inhalt</p>' },
    })
    expect(wrapper.find('.skeleton').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Inhalt')
  })

  it('zeigt den Fehler mit Wiederholen-Knopf und meldet den Klick', async () => {
    const wrapper = mount(ResourceBoundary, {
      props: { loading: false, error: 'Server weg' },
      slots: { default: '<p>Inhalt</p>' },
    })
    expect(wrapper.text()).toContain('Server weg')
    expect(wrapper.text()).not.toContain('Inhalt')

    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('zeigt den Leerzustand statt einer leeren Liste', () => {
    const wrapper = mount(ResourceBoundary, {
      props: { loading: false, empty: true, emptyTitle: 'Nichts da' },
      slots: { default: '<p>Inhalt</p>' },
    })
    expect(wrapper.text()).toContain('Nichts da')
    expect(wrapper.text()).not.toContain('Inhalt')
  })

  it('zeigt den Inhalt, wenn Daten da sind', () => {
    const wrapper = mount(ResourceBoundary, {
      props: { loading: false, empty: false },
      slots: { default: '<p>Inhalt</p>' },
    })
    expect(wrapper.text()).toContain('Inhalt')
  })
})

describe('StatusBadge', () => {
  it.each([
    ['done', 'Fertig'],
    ['needs_review', 'Prüfen'],
    ['failed', 'Fehler'],
    ['processing', 'Wird gelesen'],
    ['uploaded', 'In Warteschlange'],
  ] as const)('beschriftet %s als „%s"', (status, label) => {
    const wrapper = mount(StatusBadge, { props: { status } })
    expect(wrapper.text()).toBe(label)
  })
})

describe('UiMoneyInput', () => {
  it('gibt Cent nach außen, nicht Euro', async () => {
    const wrapper = mount(UiMoneyInput, { props: { modelValue: null } })
    await wrapper.find('input').setValue('1,09')
    expect(wrapper.props('modelValue')).toBeNull() // Prop bleibt, Event zählt
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([109])
  })

  it('zeigt einen vorhandenen Cent-Wert deutsch formatiert', () => {
    const wrapper = mount(UiMoneyInput, { props: { modelValue: 1234 } })
    expect(wrapper.find('input').element.value).toBe('12,34')
  })

  it('markiert unlesbare Eingaben und behält den letzten guten Wert', async () => {
    const wrapper = mount(UiMoneyInput, { props: { modelValue: 100 } })
    await wrapper.find('input').setValue('quatsch')
    expect(wrapper.find('input').attributes('aria-invalid')).toBe('true')
    // Kein Update mit einem kaputten Wert.
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('leert das Modell bei leerer Eingabe', async () => {
    const wrapper = mount(UiMoneyInput, { props: { modelValue: 100 } })
    await wrapper.find('input').setValue('')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([null])
  })
})

describe('ChartBars', () => {
  const rows = [
    { key: 1, label: 'Butter', value: '2,49 €', weight: 249 },
    { key: 2, label: 'Milch', value: '1,09 €', weight: 109 },
  ]

  it('rendert eine Zeile pro Eintrag', () => {
    const wrapper = mount(ChartBars, { props: { rows } })
    expect(wrapper.findAll('.bars__item')).toHaveLength(2)
    expect(wrapper.text()).toContain('Butter')
    expect(wrapper.text()).toContain('2,49 €')
  })

  it('skaliert die Balkenbreite auf den größten Wert', () => {
    const wrapper = mount(ChartBars, { props: { rows } })
    const fills = wrapper.findAll('.bars__fill')
    expect(fills[0].attributes('style')).toContain('width: 100%')
    // 109 / 249 ≈ 43,8 %
    expect(fills[1].attributes('style')).toMatch(/width: 43\.\d+%/)
  })

  it('meldet Klicks nur bei klickbaren Zeilen', async () => {
    const wrapper = mount(ChartBars, {
      props: { rows: [{ ...rows[0], clickable: true }, rows[1]] },
    })
    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(1)
    await buttons[0].trigger('click')
    expect(wrapper.emitted('select')).toHaveLength(1)
  })

  it('bleibt bei ausschließlich Nullwerten stabil (keine Division durch 0)', () => {
    const wrapper = mount(ChartBars, {
      props: { rows: [{ key: 1, label: 'Nix', value: '0,00 €', weight: 0 }] },
    })
    expect(wrapper.find('.bars__fill').attributes('style')).toContain('width: 2%')
  })
})

describe('ChartDonut', () => {
  it('fasst kleine Posten zu „Übrige" zusammen', () => {
    const slices = Array.from({ length: 9 }, (_, index) => ({
      key: index,
      label: `Kategorie ${index}`,
      value: '1,00 €',
      weight: 9 - index,
    }))
    const wrapper = mount(ChartDonut, { props: { slices, maxSlices: 4 } })

    // 3 größte + eine Sammelposition
    expect(wrapper.findAll('.donut__entry')).toHaveLength(4)
    expect(wrapper.text()).toContain('Übrige (6)')
  })

  it('rechnet Anteile aus den Gewichten', async () => {
    const wrapper = mount(ChartDonut, {
      props: {
        slices: [
          { key: 'a', label: 'A', value: '', weight: 75 },
          { key: 'b', label: 'B', value: '', weight: 25 },
        ],
      },
    })
    await nextTick()
    expect(wrapper.text()).toContain('75 %')
    expect(wrapper.text()).toContain('25 %')
  })

  it('stürzt bei leerer Eingabe nicht ab', () => {
    const wrapper = mount(ChartDonut, { props: { slices: [] } })
    expect(wrapper.findAll('.donut__entry')).toHaveLength(0)
  })
})
