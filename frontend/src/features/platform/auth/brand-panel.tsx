/** 登录页左侧品牌面板：品牌、标语、要点与晶圆图装饰。 */
import { t } from '@/i18n'
import { Building2, GitFork, Layers, ShieldCheck } from 'lucide-react'
import type { Branding } from '@/lib/branding'
import { cn } from '@/lib/utils'

/** 品牌标识：Logo 方块 + 应用名 + 副标题（与侧栏头部一致）。 */
export function BrandMark({
  branding,
  inverted,
  className,
}: {
  branding: Branding
  inverted?: boolean
  className?: string
}) {
  return (
    <div className={cn('flex min-w-0 items-center gap-3', className)}>
      {branding.logo ? (
        <img
          src={branding.logo}
          alt=''
          className='size-9 shrink-0 rounded-lg object-contain'
        />
      ) : (
        <div
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-lg',
            inverted
              ? 'bg-primary-foreground/10 ring-1 ring-primary-foreground/20 dark:bg-muted dark:ring-border'
              : 'bg-primary text-primary-foreground'
          )}
        >
          <Building2 className='size-4.5' />
        </div>
      )}
      <div className='grid min-w-0 leading-tight'>
        <span className='truncate font-semibold'>{branding.appName}</span>
        {branding.subtitle && (
          <span
            className={cn(
              'truncate text-xs',
              inverted ? 'text-primary-foreground/70' : 'text-muted-foreground'
            )}
          >
            {branding.subtitle}
          </span>
        )}
      </div>
    </div>
  )
}

const FEATURES = [
  { icon: Layers, key: 'featLot' },
  { icon: ShieldCheck, key: 'featQuality' },
  { icon: GitFork, key: 'featTrace' },
] as const

/** 大屏左侧面板；配置了登录背景图时以其为底。 */
export function BrandPanel({ branding }: { branding: Branding }) {
  const bg = branding.loginBackground
  return (
    <aside
      className='relative hidden flex-col justify-between overflow-hidden bg-primary bg-cover bg-center p-10 text-primary-foreground lg:flex dark:border-e dark:bg-card dark:text-card-foreground'
      style={bg ? { backgroundImage: `url(${bg})` } : undefined}
      data-testid='brand-panel'
    >
      {bg ? (
        <div className='absolute inset-0 bg-linear-to-t from-black/70 via-black/20 to-black/40' />
      ) : (
        <WaferArt
          className='absolute -end-28 -bottom-28 size-[480px] opacity-30 dark:opacity-20'
          style={{ maskImage: FADE, WebkitMaskImage: FADE }}
        />
      )}
      <BrandMark branding={branding} inverted className='relative' />
      <div className='relative max-w-md space-y-8'>
        <h2 className='text-2xl leading-snug font-semibold tracking-tight break-keep xl:text-3xl'>
          {t('auth.tagline')}
        </h2>
        <ul className='space-y-5'>
          {FEATURES.map(({ icon: Icon, key }) => (
            <li key={key} className='flex gap-3'>
              <div className='flex size-8 shrink-0 items-center justify-center rounded-md bg-primary-foreground/10 ring-1 ring-primary-foreground/15 dark:bg-muted dark:ring-border'>
                <Icon className='size-4' />
              </div>
              <div className='grid gap-0.5'>
                <span className='text-sm font-medium'>{t(`auth.${key}`)}</span>
                <span className='text-sm opacity-70'>
                  {t(`auth.${key}Desc`)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      </div>
      <div />
    </aside>
  )
}

const FADE = 'radial-gradient(circle at 70% 70%, black 35%, transparent 75%)'
const N = 18
const CELL = 200 / N

/** 晶圆 Bin Map 风格的装饰图（确定性图案，少量不良 die 着色）。 */
function WaferArt({
  className,
  style,
}: {
  className?: string
  style?: React.CSSProperties
}) {
  const dies: { x: number; y: number; bad: boolean; o: number }[] = []
  for (let i = 0; i < N; i++)
    for (let j = 0; j < N; j++) {
      const cx = (i + 0.5) * CELL - 100
      const cy = (j + 0.5) * CELL - 100
      if (Math.hypot(cx, cy) > 92) continue
      const h = (i * 7919 + j * 104729) % 101
      dies.push({
        x: i * CELL,
        y: j * CELL,
        bad: h < 6,
        o: 0.35 + (h % 5) * 0.12,
      })
    }
  return (
    <svg viewBox='0 0 200 200' aria-hidden className={className} style={style}>
      <circle
        cx='100'
        cy='100'
        r='98'
        fill='none'
        stroke='currentColor'
        strokeWidth='1'
      />
      {dies.map((d) => (
        <rect
          key={`${d.x}-${d.y}`}
          x={d.x + 1}
          y={d.y + 1}
          width={CELL - 2}
          height={CELL - 2}
          rx='1'
          className={d.bad ? 'fill-amber-400' : 'fill-current'}
          opacity={d.bad ? 0.7 : d.o}
        />
      ))}
      <path d='M94 198 L100 192 L106 198' fill='none' stroke='currentColor' />
    </svg>
  )
}
