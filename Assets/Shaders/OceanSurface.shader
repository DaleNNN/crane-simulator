Shader "Custom/OceanSurface"
{
    Properties
    {
        _DeepColor ("Dypt vann", Color) = (0.02, 0.10, 0.20, 1)
        _ShallowColor ("Grunt vann", Color) = (0.08, 0.32, 0.42, 1)
        _FoamColor ("Skum", Color) = (0.85, 0.92, 0.95, 1)

        _WaveHeight ("Bolgehoyde", Range(0, 3)) = 0.8
        _WaveSpeed ("Bolgefart", Range(0, 3)) = 0.6
        _WaveScale ("Bolgeskala", Range(0.005, 0.2)) = 0.03

        _FoamThreshold ("Skumterskel", Range(0, 1)) = 0.6
        _Smoothness ("Glans", Range(0, 1)) = 0.9
        _Metallic ("Metallisk", Range(0, 1)) = 0.1
    }

    SubShader
    {
        Tags
        {
            "RenderType" = "Opaque"
            "RenderPipeline" = "UniversalPipeline"
        }
        LOD 200

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma target 3.0

            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS_CASCADE
            #pragma multi_compile _ _ADDITIONAL_LIGHTS
            #pragma multi_compile_fog

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _DeepColor;
                float4 _ShallowColor;
                float4 _FoamColor;
                float _WaveHeight;
                float _WaveSpeed;
                float _WaveScale;
                float _FoamThreshold;
                float _Smoothness;
                float _Metallic;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS   : NORMAL;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS   : TEXCOORD1;
                float  waveHeight : TEXCOORD2;
                float  fogCoord   : TEXCOORD3;
            };

            float WaveSum(float2 p, float t)
            {
                float w = 0;
                w += sin(p.x * _WaveScale * 1.0 + t * 1.0) * 1.00;
                w += sin(p.y * _WaveScale * 1.3 + t * 0.8) * 0.70;
                w += sin((p.x + p.y) * _WaveScale * 0.7 + t * 1.3) * 0.50;
                w += sin((p.x - p.y) * _WaveScale * 1.9 + t * 0.5) * 0.30;
                return w / 2.5;
            }

            Varyings vert(Attributes IN)
            {
                Varyings OUT;

                float3 posWS = TransformObjectToWorld(IN.positionOS.xyz);
                float t = _Time.y * _WaveSpeed;

                float h = WaveSum(posWS.xz, t);
                posWS.y += h * _WaveHeight;

                float d = 2.0;
                float hx = WaveSum(posWS.xz + float2(d, 0), t);
                float hz = WaveSum(posWS.xz + float2(0, d), t);

                float3 tx = float3(d, (hx - h) * _WaveHeight, 0);
                float3 tz = float3(0, (hz - h) * _WaveHeight, d);
                float3 n = normalize(cross(tz, tx));

                OUT.positionWS = posWS;
                OUT.positionCS = TransformWorldToHClip(posWS);
                OUT.normalWS = n;
                OUT.waveHeight = h;
                OUT.fogCoord = ComputeFogFactor(OUT.positionCS.z);

                return OUT;
            }

            half4 frag(Varyings IN) : SV_Target
            {
                float blend = saturate(IN.waveHeight * 0.5 + 0.5);
                float3 baseColor = lerp(_DeepColor.rgb, _ShallowColor.rgb, blend);

                float foam = smoothstep(_FoamThreshold, _FoamThreshold + 0.25, IN.waveHeight);
                baseColor = lerp(baseColor, _FoamColor.rgb, foam);

                InputData inputData = (InputData)0;
                inputData.positionWS = IN.positionWS;
                inputData.normalWS = normalize(IN.normalWS);
                inputData.viewDirectionWS = GetWorldSpaceNormalizeViewDir(IN.positionWS);
                inputData.shadowCoord = TransformWorldToShadowCoord(IN.positionWS);
                inputData.fogCoord = IN.fogCoord;

                SurfaceData surfaceData = (SurfaceData)0;
                surfaceData.albedo = baseColor;
                surfaceData.metallic = _Metallic;
                surfaceData.smoothness = _Smoothness * (1 - foam * 0.7);
                surfaceData.occlusion = 1;
                surfaceData.alpha = 1;

                half4 color = UniversalFragmentPBR(inputData, surfaceData);
                color.rgb = MixFog(color.rgb, IN.fogCoord);

                return color;
            }
            ENDHLSL
        }
    }

    FallBack "Universal Render Pipeline/Lit"
}