using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography.X509Certificates;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using Opc.Ua;
using Opc.Ua.Client;

public class CraneOpcClient : MonoBehaviour
{
    [Header("Server")]
    [SerializeField] string serverUrl = "opc.tcp://192.168.172.242:4840";

    [Header("Sertifikat (ligger i Assets/StreamingAssets)")]
    [SerializeField] string certFileName = "UnityCraneClient.pfx";
    [SerializeField] string certPassword = "unityopcua";

    [Header("Node-ID-er (ns=1)")]
    [SerializeField] string slewNode = "Crane.SlewAngle";
    [SerializeField] string boomNode = "Crane.BoomAngle";
    [SerializeField] string telescopeNode = "Crane.TelescopeExtension";

    [Header("Kran")]
    [SerializeField] CraneController crane;
    [SerializeField] int publishingIntervalMs = 50;

    // Settes fra OPC-traden, leses i Update()
    volatile float slew, boom, telescope;
    volatile bool connected;

    Session session;

    // Unity-API kan ikke kalles fra bakgrunnstrad, sa stien caches her
    string certFullPath;

    void Start()
    {
        certFullPath = Path.Combine(Application.streamingAssetsPath, certFileName);
        Debug.Log("Sertifikatsti: " + certFullPath);

        Task.Run(async () =>
        {
            SynchronizationContext.SetSynchronizationContext(null);
            try { await Connect(); }
            catch (Exception e) { Debug.LogError("OPC UA feilet: " + e.Message); }
        });
    }

    void Update()
    {
        if (!connected || crane == null) return;

        crane.slewAngle = slew;
        crane.boomAngle = boom;
        crane.telescopeExtension = telescope;
    }

    async Task Connect()
    {
        if (!File.Exists(certFullPath))
        {
            Debug.LogError("Fant ikke sertifikat: " + certFullPath);
            return;
        }

        var cert = new X509Certificate2(
            certFullPath,
            certPassword,
            X509KeyStorageFlags.Exportable | X509KeyStorageFlags.PersistKeySet);

        Debug.Log("Sertifikat lastet. HasPrivateKey = " + cert.HasPrivateKey);

        var config = new ApplicationConfiguration
        {
            ApplicationName = "UnityCraneClient",
            ApplicationUri = "urn:UnityCraneClient",
            ApplicationType = ApplicationType.Client,

            SecurityConfiguration = new SecurityConfiguration
            {
                ApplicationCertificate = new CertificateIdentifier { Certificate = cert },
                AutoAcceptUntrustedCertificates = true,
                RejectSHA1SignedCertificates = false,
                MinimumCertificateKeySize = 1024,
                TrustedPeerCertificates = new CertificateTrustList(),
                TrustedIssuerCertificates = new CertificateTrustList(),
                RejectedCertificateStore = new CertificateTrustList()
            },

            TransportConfigurations = new TransportConfigurationCollection(),
            TransportQuotas = new TransportQuotas { OperationTimeout = 15000 },
            ClientConfiguration = new ClientConfiguration { DefaultSessionTimeout = 60000 },
            TraceConfiguration = new TraceConfiguration()
        };

        await config.Validate(ApplicationType.Client);
        config.CertificateValidator.AutoAcceptUntrustedCertificates = true;

        // --- Discovery ---
        var endpointConfig = EndpointConfiguration.Create(config);
        EndpointDescription endpoint;

        using (var dc = DiscoveryClient.Create(new Uri(serverUrl), endpointConfig))
        {
            endpoint = dc.GetEndpoints(null)
                         .First(e => e.SecurityMode == MessageSecurityMode.None);
        }

        // --- Sesjon ---
        session = await Session.Create(
            config, new ConfiguredEndpoint(null, endpoint, endpointConfig),
            false, "UnityCraneSession", 60000,
            new UserIdentity(new AnonymousIdentityToken()), null);

        Debug.Log("OPC UA tilkoblet: " + endpoint.EndpointUrl);

        // --- Abonnement ---
        var subscription = new Subscription(session.DefaultSubscription)
        {
            PublishingInterval = publishingIntervalMs
        };

        subscription.AddItem(MakeItem(slewNode, v => slew = v));
        subscription.AddItem(MakeItem(boomNode, v => boom = v));
        subscription.AddItem(MakeItem(telescopeNode, v => telescope = v));

        session.AddSubscription(subscription);
        subscription.Create();

        connected = true;
        Debug.Log("Abonnerer pa kranverdier.");
    }

    MonitoredItem MakeItem(string identifier, Action<float> setter)
    {
        var item = new MonitoredItem
        {
            DisplayName = identifier,
            StartNodeId = new NodeId(identifier, 1),
            AttributeId = Attributes.Value,
            SamplingInterval = publishingIntervalMs,
            QueueSize = 1,
            DiscardOldest = true
        };

        item.Notification += (mi, args) =>
        {
            foreach (var value in mi.DequeueValues())
            {
                if (StatusCode.IsGood(value.StatusCode))
                    setter(Convert.ToSingle(value.Value));
            }
        };

        return item;
    }

    void OnDestroy()
    {
        connected = false;
        try { session?.Close(); } catch { }
    }
}