/** 系统配置分组卡片。 */
import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { ChevronDown, Loader2, RotateCcw, Save, Undo2 } from 'lucide-react'
import { toast } from 'sonner'
import { api, type ConfigGroup, type ConfigItem } from '@/lib/api'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Label } from '@/components/ui/label'
import { ConfigField } from './config-field'

type Scope = 'tenant' | 'platform'

/** 服务端值 -> 表单值（JSON 以格式化文本编辑） */
const toForm = (item: ConfigItem, v: unknown) =>
  item.value_type === 'json' ? JSON.stringify(v ?? null, null, 2) : (v ?? '')

const groupTitle = (g: ConfigGroup) =>
  g.name_key ? t(g.name_key, { defaultValue: g.name }) : g.name
const itemTitle = (g: ConfigGroup, i: ConfigItem) =>
  t(`config.items.${g.code}.${i.code}`, { defaultValue: i.name })
const itemDesc = (g: ConfigGroup, i: ConfigItem) =>
  t(`config.itemDescs.${g.code}.${i.code}`, {
    defaultValue: i.description ?? '',
  })

/** 每个分组一张可折叠卡片（默认折叠）：编辑后保存 / 重置。
 *  不支持新增 / 删除。租户范围内每项会显示是否继承自平台，
 *  并可重置为平台值。 */
export function ConfigGroupCard({
  group,
  scope,
  canEdit,
  tenantId,
}: {
  group: ConfigGroup
  scope: Scope
  canEdit: boolean
  /** 平台控制台编辑指定租户的覆盖值（品牌）；为空时作用于当前租户 */
  tenantId?: string
}) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const initial = useMemo(
    () =>
      Object.fromEntries(group.items.map((i) => [i.code, toForm(i, i.value)])),
    [group]
  )
  const [draft, setDraft] = useState<Record<string, unknown>>(initial)
  const [base, setBase] = useState(initial)
  if (base !== initial) {
    // 服务端数据变化（已保存 / 重新获取）：以其重置表单
    setBase(initial)
    setDraft(initial)
  }

  const errors: Record<string, string> = {}
  for (const i of group.items)
    if (i.value_type === 'json') {
      try {
        JSON.parse(String(draft[i.code] ?? 'null'))
      } catch {
        errors[i.code] = t('config.invalidJson')
      }
    }
  const changed = group.items.filter(
    (i) => JSON.stringify(draft[i.code]) !== JSON.stringify(initial[i.code])
  )
  const done = () => {
    // 同时刷新列表与公开品牌信息（侧栏、标题、favicon、页脚）
    qc.invalidateQueries({ queryKey: ['config'] })
    if (tenantId) qc.invalidateQueries({ queryKey: ['platform', 'branding'] })
  }
  const save = useMutation({
    mutationFn: () => {
      const values = Object.fromEntries(
        changed.map((i) => [
          i.code,
          i.value_type === 'json'
            ? JSON.parse(String(draft[i.code]))
            : draft[i.code],
        ])
      )
      if (scope === 'tenant' && tenantId)
        return api.platform.updateBranding(tenantId, group.code, values)
      return scope === 'tenant'
        ? api.config.updateTenant(group.code, values)
        : api.config.updatePlatform(group.code, values)
    },
    onSuccess: () => {
      toast.success(t('config.saved'))
      done()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })
  const resetItem = useMutation({
    mutationFn: (code: string) =>
      tenantId
        ? api.platform.updateBranding(tenantId, group.code, { [code]: null })
        : api.config.resetTenantItem(group.code, code),
    onSuccess: () => {
      toast.success(t('config.resetDone'))
      done()
    },
    onError: (e) => toast.error(errorMessage(e)),
  })

  return (
    <Collapsible open={open} onOpenChange={setOpen} asChild>
      <Card data-testid={`config-group-${group.code}`} className='gap-0 py-0'>
        <CollapsibleTrigger asChild>
          <CardHeader className='cursor-pointer py-4 select-none'>
            <div className='flex items-center gap-2'>
              <CardTitle className='text-base'>{groupTitle(group)}</CardTitle>
              <Badge variant='outline' className='font-mono text-[10px]'>
                {group.code}
              </Badge>
              <span className='ms-auto text-xs text-muted-foreground'>
                {t('config.itemCount', { count: group.items.length })}
              </span>
              <ChevronDown
                className={cn(
                  'size-4 transition-transform',
                  open && 'rotate-180'
                )}
              />
            </div>
            {group.description && (
              <CardDescription>
                {t(`config.groupDescs.${group.code}`, {
                  defaultValue: group.description,
                })}
              </CardDescription>
            )}
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              save.mutate()
            }}
          >
            <CardContent className='space-y-5 border-t pt-5'>
              {group.items.map((i) => {
                const id = `cfg-${group.code}-${i.code}`
                return (
                  <div
                    key={i.code}
                    className='grid gap-2 md:grid-cols-[14rem_1fr]'
                  >
                    <div className='space-y-1'>
                      <Label htmlFor={id}>{itemTitle(group, i)}</Label>
                      {scope === 'tenant' && (
                        <div className='flex items-center gap-1'>
                          {i.overridden ? (
                            <Badge>{t('config.overridden')}</Badge>
                          ) : (
                            <Badge variant='secondary'>
                              {t('config.inherited')}
                            </Badge>
                          )}
                          {i.overridden && canEdit && (
                            <Button
                              type='button'
                              variant='ghost'
                              size='sm'
                              className='h-6 px-1.5 text-xs'
                              disabled={resetItem.isPending}
                              onClick={() => resetItem.mutate(i.code)}
                              title={t('config.resetToPlatform')}
                            >
                              <RotateCcw className='size-3' />
                              {t('config.resetToPlatform')}
                            </Button>
                          )}
                        </div>
                      )}
                    </div>
                    <div className='space-y-1'>
                      <fieldset disabled={!canEdit} className='contents'>
                        <ConfigField
                          id={id}
                          item={i}
                          scope={scope}
                          value={draft[i.code]}
                          error={errors[i.code]}
                          onChange={(v) =>
                            setDraft((d) => ({ ...d, [i.code]: v }))
                          }
                        />
                      </fieldset>
                      {errors[i.code] ? (
                        <p className='text-xs text-destructive'>
                          {errors[i.code]}
                        </p>
                      ) : (
                        itemDesc(group, i) && (
                          <p className='text-xs text-muted-foreground'>
                            {itemDesc(group, i)}
                          </p>
                        )
                      )}
                      {scope === 'tenant' && i.overridden && (
                        <p className='text-xs text-muted-foreground'>
                          {t('config.platformValue')}:{' '}
                          <code className='break-all'>
                            {i.platform_value === null ||
                            i.platform_value === ''
                              ? '—'
                              : String(
                                  typeof i.platform_value === 'object'
                                    ? JSON.stringify(i.platform_value)
                                    : i.platform_value
                                )}
                          </code>
                        </p>
                      )}
                    </div>
                  </div>
                )
              })}
            </CardContent>
            {canEdit && (
              <CardFooter className='justify-end gap-2 border-t py-4'>
                <span className='me-auto text-xs text-muted-foreground'>
                  {changed.length
                    ? t('config.unsaved', { count: changed.length })
                    : ''}
                </span>
                <Button
                  type='button'
                  variant='outline'
                  disabled={!changed.length || save.isPending}
                  onClick={() => setDraft(initial)}
                >
                  <Undo2 />
                  {t('config.reset')}
                </Button>
                <Button
                  type='submit'
                  disabled={
                    !changed.length ||
                    save.isPending ||
                    Object.keys(errors).length > 0
                  }
                >
                  {save.isPending ? (
                    <Loader2 className='animate-spin' />
                  ) : (
                    <Save />
                  )}
                  {t('common.save')}
                </Button>
              </CardFooter>
            )}
          </form>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}
